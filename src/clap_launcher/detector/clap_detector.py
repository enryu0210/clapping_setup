"""[3] 박수 판정 — 이 프로젝트의 심장.

전체 흐름 (자세한 근거는 docs/DETECTION.md):

  프레임(10ms)마다
     ↓
  [1] 시작점 찾기 (onset.py)  "방금 뭔가 시작됐다"
     ↓  잠깐 기다렸다가 (소리가 끝나기를 기다린다)
  [2] 최근 160ms를 꺼내 지문 검사   "그게 박수인가"
       · 음정이 없는가        → 기침·말소리 배제
       · 잡음스러운가          → 음정 있는 소리 배제
       · 고음이 강한가        → 문 닫는 소리 배제
       · 날카로운가            → 둔탁한 소리 배제
       · 짧게 끝났는가        → 종이·음악 배제
     ↓
  [3] 박수 1회 인정 → 시각 기록
     ↓
  [4] 0.15~0.8초 안에 또 한 번? → 🎉 발동

⚠️ 설계 포인트: 현재 시각을 내부에서 time.time() 으로 읽지 않고 인자로 받는다.
   그래야 테스트에서 시간을 마음대로 조작해 "0.5초 뒤 두 번째 박수" 같은 상황을
   기다리지 않고 즉시 검증할 수 있다.
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

from ..audio.features import EventFeatures, extract_event_features, high_band_dbfs
from ..config import DetectionConfig
from .onset import OnsetDetector

ANALYSIS_MS = 160.0        # 소리 하나를 판단하기 위해 들여다보는 길이
PRE_ROLL_MS = 20.0         # 시작점보다 살짝 앞에서부터 본다 (시작 순간이 잘리지 않게)
ANALYSIS_DELAY_MS = 120.0  # 시작점을 잡은 뒤 이만큼 기다렸다 분석한다 (소리가 끝나기를 기다림)


class State(Enum):
    """감지기의 현재 상태."""

    IDLE = auto()      # 대기 — 첫 박수를 기다림
    ARMED = auto()     # 첫 박수를 들음 — 제한 시간 안에 두 번째를 기다림
    COOLDOWN = auto()  # 방금 발동함 — 잠시 아무것도 감지하지 않음


@dataclass(frozen=True)
class SoundEvent:
    """분석을 마친 소리 하나. 박수가 아니어도 만들어진다(디버깅 화면에 보여주기 위해)."""

    time: float
    features: EventFeatures
    is_clap: bool
    reject_reason: str = ""      # 박수가 아니라고 판단한 이유 (비어 있으면 박수)
    triggered: bool = False      # 이 이벤트로 '짝짝'이 완성되었는가

    def describe(self) -> str:
        mark = "👏 박수" if self.is_clap else f"✗ {self.reject_reason}"
        return f"{mark} | {self.features.describe()}"


class ClapDetector:
    """소리 조각을 순서대로 받아 '짝짝'인지 판정한다."""

    def __init__(self, config: DetectionConfig, sample_rate: int) -> None:
        self.config = config
        self.sample_rate = sample_rate
        self.state = State.IDLE

        self._onset = OnsetDetector(rise_db=config.onset_rise_db)
        # 분석에 필요한 만큼의 최근 오디오를 들고 있는다
        self._buffer_size = int(sample_rate * (ANALYSIS_MS + PRE_ROLL_MS) / 1000)
        self._buffer: deque[np.ndarray] = deque()
        self._buffered_samples = 0

        self._pending_analysis_at: float | None = None   # 이 시각이 되면 분석한다
        self._last_clap_at: float | None = None
        self._cooldown_until: float | None = None

    def reset(self) -> None:
        """장치를 바꾸거나 다시 시작할 때 상태를 초기화한다."""
        self.state = State.IDLE
        self._onset.reset()
        self._buffer.clear()
        self._buffered_samples = 0
        self._pending_analysis_at = None
        self._last_clap_at = None
        self._cooldown_until = None

    # ── 메인 진입점 ───────────────────────────────────────
    def feed(self, frame: np.ndarray, now: float) -> SoundEvent | None:
        """프레임 하나를 넣는다. 소리 하나의 분석이 끝난 순간에만 결과를 돌려준다.

        '짝짝'이 완성됐는지는 결과의 triggered 로 확인한다.
        박수가 아닌 소리도 결과를 돌려주는데, 디버깅 화면에서 "무엇을 왜 걸렀는지"
        보여주기 위해서다. 튜닝할 때 이 정보가 없으면 원인을 못 찾는다.
        """
        self._push(frame)

        # 쿨다운이 끝났으면 대기 상태로 돌아간다
        if self._cooldown_until is not None and now >= self._cooldown_until:
            self._cooldown_until = None
            self.state = State.IDLE

        # 첫 박수를 듣고 너무 오래 지났으면 잊는다.
        # ⚠️ 시간 기준을 맞추는 게 중요하다. _last_clap_at 은 '소리가 난 시각'인데
        #    now 는 '지금 프레임 시각'이라, 그대로 비교하면 분석 지연(120ms)만큼
        #    간격이 부풀려져서 허용 범위 안의 박수를 놓친다. now 도 소리 기준으로 바꿔 비교한다.
        if (self.state == State.ARMED and self._last_clap_at is not None
                and (self._sound_time(now) - self._last_clap_at) * 1000
                > self.config.max_interval_ms):
            self.state = State.IDLE
            self._last_clap_at = None

        # 시작점을 잡은 뒤 소리가 끝나길 기다렸다가 분석한다
        if self._pending_analysis_at is not None:
            if now >= self._pending_analysis_at:
                self._pending_analysis_at = None
                return self._analyze(now)
            return None

        if self._onset.feed(high_band_dbfs(frame, self.sample_rate), now):
            self._pending_analysis_at = now + ANALYSIS_DELAY_MS / 1000.0
        return None

    # ── 내부 구현 ─────────────────────────────────────────
    @staticmethod
    def _sound_time(now: float) -> float:
        """'지금 프레임 시각'을 '소리가 실제로 난 시각'으로 되돌린다.

        분석은 소리가 끝나길 기다렸다가 하므로 항상 ANALYSIS_DELAY_MS 만큼 늦다.
        간격 계산은 반드시 이 함수를 거친 값끼리 해야 한다.
        """
        return now - ANALYSIS_DELAY_MS / 1000.0

    def _push(self, frame: np.ndarray) -> None:
        """최근 오디오를 정해진 길이만큼만 들고 있는다 (오래된 것부터 버린다)."""
        self._buffer.append(frame)
        self._buffered_samples += frame.size
        while self._buffered_samples - self._buffer[0].size >= self._buffer_size:
            self._buffered_samples -= self._buffer.popleft().size

    def _recent_segment(self) -> np.ndarray:
        """분석할 최근 구간을 하나의 배열로 합쳐 돌려준다."""
        if not self._buffer:
            return np.array([], dtype=np.float32)
        return np.concatenate(self._buffer)[-self._buffer_size:]

    def _analyze(self, now: float) -> SoundEvent:
        """모아둔 소리를 분석해 박수인지 판정하고, 짝짝 완성 여부까지 처리한다."""
        features = extract_event_features(self._recent_segment(), self.sample_rate)
        reason = self._reject_reason(features)

        if reason:
            return SoundEvent(time=now, features=features, is_clap=False, reject_reason=reason)

        # 쿨다운 중이면 박수로 인정은 하되 발동시키지 않는다
        if self._cooldown_until is not None:
            return SoundEvent(time=now, features=features, is_clap=True,
                              reject_reason="쿨다운 중")

        # 두 번째 박수인지 확인한다.
        # 시각 기준을 '분석 시각'이 아니라 '소리가 난 시각'으로 맞추기 위해
        # 분석 지연만큼 빼준다. 안 그러면 간격이 실제보다 길게 나온다.
        clap_at = self._sound_time(now)

        if self.state == State.ARMED and self._last_clap_at is not None:
            gap_ms = (clap_at - self._last_clap_at) * 1000
            if self.config.min_interval_ms <= gap_ms <= self.config.max_interval_ms:
                self.state = State.COOLDOWN
                self._cooldown_until = now + self.config.cooldown_sec
                self._last_clap_at = None
                return SoundEvent(time=now, features=features, is_clap=True, triggered=True)
            if gap_ms < self.config.min_interval_ms:
                # 너무 빠르다 = 첫 박수의 여운일 가능성이 높다. 첫 박수 기억은 유지한다.
                return SoundEvent(time=now, features=features, is_clap=True,
                                  reject_reason="간격이 너무 짧음")

        # 첫 박수로 기록한다
        self.state = State.ARMED
        self._last_clap_at = clap_at
        return SoundEvent(time=now, features=features, is_clap=True)

    def _reject_reason(self, f: EventFeatures) -> str:
        """박수가 아니라고 판단한 이유. 박수면 빈 문자열.

        이유를 문자열로 남기는 이유: 튜닝할 때 "왜 안 잡히지?"를 화면에서 바로 알 수 있다.
        조건 순서는 확실한 것부터 — 가장 강력한 판별인 '음정'을 먼저 본다.
        """
        c = self.config
        if f.harmonicity > c.max_harmonicity:
            return f"음정이 있음({f.harmonicity:.2f}) — 기침·말소리"
        if f.high_freq_ratio < c.min_high_freq_ratio:
            return f"고음이 부족({f.high_freq_ratio:.2f}) — 둔탁한 소리"
        if f.zero_crossing_rate < c.min_zero_crossing_rate:
            return f"날카롭지 않음({f.zero_crossing_rate:.2f})"
        if f.flatness < c.min_flatness:
            return f"잡음스럽지 않음({f.flatness:.2f})"
        if f.flatness > c.max_flatness:
            # 백색잡음에 너무 가깝다 = 순수한 '딸깍'. 박수는 오므린 손바닥이 울림통 역할을 해서
            # 스펙트럼에 굴곡이 생기는데, 키보드 같은 기계적 타격음은 그 굴곡이 없다.
            return f"너무 밋밋한 잡음({f.flatness:.2f}) — 키보드·딸깍 소리"
        if f.decay_ms > c.max_decay_ms:
            return f"너무 길게 이어짐({f.decay_ms:.0f}ms) — 종이·음악"
        if f.decay_ms < c.min_decay_ms:
            # 박수는 손바닥이 부딪힌 뒤 잠깐 울린다. 키보드·마우스 딸깍은 그 울림이 없어
            # 훨씬 짧게 끝난다. (실측: 박수 26ms, 키보드 10ms)
            return f"너무 짧음({f.decay_ms:.0f}ms) — 키보드·클릭"
        return ""
