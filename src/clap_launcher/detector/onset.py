"""시작점(onset) 찾기 — "방금 뭔가 시작됐다"를 잡는다.

박수인지 아닌지는 여기서 판단하지 않는다. 그건 다음 단계(clap_detector)의 일이다.
여기서는 **분석할 가치가 있는 순간**만 골라낸다.

⚠️ 절대 음량으로 판단하지 않는 이유 (이 프로젝트의 핵심 제약):
리미터(클리핑 가드)가 걸린 마이크는 큰 소리를 눌러버려서 "얼마나 큰가"가 의미를 잃는다.
대신 **'최근 배경 대비 얼마나 갑자기 뛰었나'** 라는 변화량을 본다.
리미터가 전체 볼륨을 절반으로 깎아도, 배경과 박수가 함께 깎이므로 '차이'는 유지된다.

기준선으로 평균이 아니라 **중앙값(median)** 을 쓰는 이유:
평균은 큰 소리 하나에 끌려 올라간다. 박수를 치면 기준선이 같이 올라가서
바로 뒤에 오는 두 번째 박수를 놓친다. 중앙값은 그런 순간값에 흔들리지 않는다.
"""

from collections import deque

import numpy as np

HISTORY_MS = 500.0    # 배경 기준선을 계산할 구간
GUARD_MS = 60.0       # 최근 이 구간은 기준선 계산에서 뺀다 (지금 나는 소리가 기준선을 올리지 않도록)
WARMUP_MS = 250.0     # 이만큼 들어봐야 기준선을 믿을 수 있다 (프로그램 시작 직후 오작동 방지)


class OnsetDetector:
    """고음 에너지가 배경 대비 갑자기 뛰는 순간을 잡는다."""

    def __init__(self, rise_db: float = 8.0, refractory_ms: float = 80.0) -> None:
        """
        Args:
            rise_db: 배경 대비 몇 dB 뛰어야 시작점으로 볼지
            refractory_ms: 한 번 잡은 뒤 이만큼은 다시 잡지 않는다 (같은 소리의 여운 무시)
        """
        self.rise_db = rise_db
        self.refractory_sec = refractory_ms / 1000.0
        self._history: deque[tuple[float, float]] = deque()   # (시각, 고음 dB)
        self._last_onset: float | None = None

    def reset(self) -> None:
        """장치를 바꾸거나 다시 시작할 때 기억을 지운다."""
        self._history.clear()
        self._last_onset = None

    @property
    def floor_db(self) -> float | None:
        """현재 배경 기준선. 아직 충분히 못 들었으면 None."""
        if not self._history:
            return None
        newest = self._history[-1][0]
        # 최근 GUARD_MS 를 뺀 값들만 사용한다
        older = [db for t, db in self._history if newest - t >= GUARD_MS / 1000.0]
        if len(older) < 5:
            return None
        return float(np.median(older))

    def feed(self, high_db: float, now: float) -> bool:
        """프레임 하나를 넣는다. 시작점이면 True.

        Args:
            high_db: 이 프레임의 고음 대역 에너지 (dB)
            now: 현재 시각(초). 테스트에서 조작할 수 있도록 밖에서 받는다.
        """
        self._history.append((now, high_db))
        # 오래된 기록을 버린다
        while self._history and now - self._history[0][0] > HISTORY_MS / 1000.0:
            self._history.popleft()

        # 충분히 들어보기 전에는 판단하지 않는다
        if now - self._history[0][0] < WARMUP_MS / 1000.0:
            return False

        floor = self.floor_db
        if floor is None:
            return False

        # 방금 잡았으면 잠시 쉰다 (한 번의 박수를 여러 번으로 세지 않기 위해)
        if self._last_onset is not None and now - self._last_onset < self.refractory_sec:
            return False

        if high_db - floor >= self.rise_db:
            self._last_onset = now
            return True
        return False
