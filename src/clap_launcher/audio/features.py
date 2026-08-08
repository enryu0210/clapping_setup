"""[2] 특징 추출 — 소리 조각을 '숫자 지문'으로 바꾼다.

두 종류로 나뉜다.

  프레임 특징 (10ms마다, 매우 자주)  : 음량·고음 에너지. "뭔가 시작됐나?" 판단용.
  이벤트 특징 (소리가 났을 때 한 번) : 하모니시티·평탄도 등. "그게 박수인가?" 판단용.

⚠️ 여기 있는 특징들의 공통점: **전부 '비율'이다.**
   소리 전체에 2를 곱하든 0.5를 곱하든 값이 거의 변하지 않는다.
   리미터(클리핑 가드)가 하는 일이 정확히 '곱하기'이므로, 이 특징들은 리미터를 견딘다.
   반대로 crest_factor 나 절대 음량은 리미터가 직접 겨냥해 없애는 값이라 판정에 쓰지 않는다.
   자세한 근거는 docs/DETECTION.md 참고.
"""

import math
from dataclasses import dataclass

import numpy as np

HIGH_FREQ_CUTOFF_HZ = 2000     # 이 위쪽을 '고음'으로 본다. 박수의 특징 대역.
SILENCE_DBFS = -120.0          # 완전한 무음을 표시할 때 쓰는 하한값 (log(0) 방지)
PITCH_MIN_HZ = 70.0            # 사람 목소리 최저 음정 (성인 남성 저음)
PITCH_MAX_HZ = 500.0           # 사람 목소리 최고 음정 (기침·비명 포함)
PITCH_LOWPASS_HZ = 1600.0      # 음정을 찾을 때는 고음을 걷어낸다 (아래 harmonicity 설명 참고)
EPS = 1e-12                    # 0으로 나누기·log(0) 방지용


# ── 프레임 특징 (10ms마다) ────────────────────────────────

def compute_rms(frame: np.ndarray) -> float:
    """조각의 실효값(RMS). 사람이 느끼는 '소리 크기'에 가장 가까운 지표.

    단순 평균이 아니라 제곱평균제곱근을 쓰는 이유:
    소리 파형은 +와 -를 오가서 그냥 평균 내면 0에 가까워진다. 제곱하면 부호가 사라진다.
    """
    if frame.size == 0:
        return 0.0
    # float32 로 계산하면 값이 작을 때 오차가 커서 float64 로 올려 계산한다.
    return float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))


def rms_to_dbfs(rms: float) -> float:
    """RMS(0~1)를 dBFS로 바꾼다. 사람이 읽기 좋은 눈금을 만들기 위한 표시 전용 함수.

    RMS는 0.001과 0.01의 차이가 눈에 안 들어오지만, dB로 바꾸면 -60dB / -40dB 로
    일정한 간격이 된다. 조용한 방(-60dB)과 박수(-10dB)를 한 화면에 그릴 수 있다.
    """
    if rms <= 0.0:
        return SILENCE_DBFS
    return max(SILENCE_DBFS, 20.0 * math.log10(rms))


def high_band_dbfs(frame: np.ndarray, sample_rate: int,
                   cutoff_hz: float = HIGH_FREQ_CUTOFF_HZ) -> float:
    """고음 대역(기본 2kHz 이상)의 에너지를 dB로.

    시작점(onset)을 찾을 때 전체 음량이 아니라 이 값을 쓰는 이유:
    에어컨 소리, 컴퓨터 팬, 차 소리 같은 배경 잡음은 대부분 저음이다.
    고음만 보면 그런 잡음에 기준선이 흔들리지 않는다.
    """
    if frame.size == 0:
        return SILENCE_DBFS
    spectrum = np.fft.rfft(frame)
    power = np.abs(spectrum) ** 2
    freqs = np.fft.rfftfreq(frame.size, d=1.0 / sample_rate)
    high_power = float(power[freqs >= cutoff_hz].sum())
    if high_power <= 0.0:
        return SILENCE_DBFS
    # 프레임 길이에 따라 값이 달라지지 않도록 샘플 수로 나눈다
    return max(SILENCE_DBFS, 10.0 * math.log10(high_power / frame.size + EPS))


# ── 이벤트 특징 (소리가 났을 때 한 번) ─────────────────────

@dataclass(frozen=True)
class EventFeatures:
    """소리 조각 하나의 '지문'. 각 값의 의미는 docs/DETECTION.md 3장 참고."""

    high_freq_ratio: float   # 고음 비율 (0~1). 박수 높음, 문 닫는 소리 낮음
    flatness: float          # 스펙트럼 평탄도 (0~1). 잡음스러울수록 높음. 박수 높음
    zero_crossing_rate: float  # 영교차율 (0~1). 날카로울수록 높음. 박수 높음
    harmonicity: float       # 음정이 있는 정도 (0~1). 기침·말 높음, 박수 낮음
    decay_ms: float          # 정점 이후 잦아들기까지 시간. 박수 짧음, 종이·음악 김
    crest_factor: float      # 최대값/RMS. 진단용으로만 쓴다 (리미터가 파괴하는 값)
    peak: float              # 조각 안의 최대 진폭 (0~1)

    def describe(self) -> str:
        """디버깅 화면에 한 줄로 뿌리기 위한 요약."""
        return (
            f"고음 {self.high_freq_ratio:.2f} | 평탄도 {self.flatness:.2f} | "
            f"ZCR {self.zero_crossing_rate:.2f} | 음정 {self.harmonicity:.2f} | "
            f"길이 {self.decay_ms:.0f}ms"
        )


def compute_high_freq_ratio(segment: np.ndarray, sample_rate: int,
                            cutoff_hz: float = HIGH_FREQ_CUTOFF_HZ) -> float:
    """전체 에너지 대비 고음(기본 2kHz 이상) 에너지 비율 (0.0~1.0).

    왜 필요한가: 문 닫는 소리 '쿵'은 박수만큼 크지만 저음이라 이 값이 낮다.
    음량만 보면 절대 못 거르는 오탐을 여기서 걸러낸다.
    """
    if segment.size == 0:
        return 0.0
    power = np.abs(np.fft.rfft(segment)) ** 2
    freqs = np.fft.rfftfreq(segment.size, d=1.0 / sample_rate)
    total = float(power.sum())
    if total <= EPS:
        return 0.0
    return float(power[freqs >= cutoff_hz].sum() / total)


def compute_flatness(segment: np.ndarray) -> float:
    """스펙트럼 평탄도 (0.0~1.0). '잡음스러운 정도'.

    주파수 성분이 고르게 퍼져 있으면 1에 가깝고(잡음),
    특정 주파수에 몰려 있으면 0에 가깝다(음정 있는 소리).

    박수는 공기가 터지는 잡음이라 높고, 말소리·기침은 성대 진동 때문에 낮다.
    기하평균 ÷ 산술평균으로 계산하는데, 기하평균을 그냥 곱해서 구하면
    값이 너무 작아져 0이 되어버리므로 로그로 바꿔서 계산한다.
    """
    if segment.size == 0:
        return 0.0
    power = np.abs(np.fft.rfft(segment)) ** 2
    power = power[1:]          # 0Hz(DC) 성분은 소리가 아니므로 뺀다
    if power.size == 0:
        return 0.0
    arithmetic_mean = float(power.mean())
    if arithmetic_mean <= EPS:
        return 0.0
    geometric_mean = float(np.exp(np.mean(np.log(power + EPS))))
    return min(1.0, geometric_mean / arithmetic_mean)


def compute_zero_crossing_rate(segment: np.ndarray) -> float:
    """영교차율 (0.0~1.0). 파형이 0선을 가로지르는 비율.

    날카롭고 고음이 많은 소리일수록 높다. 계산이 FFT보다 훨씬 싸면서
    고음 비율과 비슷한 정보를 주기 때문에, 서로 보완하는 용도로 함께 쓴다.
    """
    if segment.size < 2:
        return 0.0
    signs = np.signbit(segment)
    return float(np.count_nonzero(signs[1:] != signs[:-1]) / (segment.size - 1))


def compute_harmonicity(segment: np.ndarray, sample_rate: int) -> float:
    """음정이 있는 정도 (0.0~1.0). **기침과 박수를 가르는 결정적 특징.**

    원리(자기상관):
    파형을 조금씩 밀어서 자기 자신과 비교했을 때, 잘 겹치는 지점이 있으면
    그만큼 규칙적으로 반복된다는 뜻 = 음정이 있다는 뜻이다.

        박수:  불규칙 → 아무리 밀어도 잘 안 겹침 → 낮은 값
        기침:  성대 진동이 섞여 주기적 → 특정 지점에서 확 겹침 → 높은 값

    고음을 먼저 걷어내는 이유:
    음정 성분은 낮은 주파수에 있는데, 박수 같은 고음 잡음이 섞여 있으면
    겹침 계산이 흐려진다. 목소리 대역만 남기면 판별이 훨씬 또렷해진다.
    """
    if segment.size < 4:
        return 0.0

    # ── 1) 고음 제거 (FFT로 높은 주파수를 0으로 만들고 되돌린다) ──
    spectrum = np.fft.rfft(segment)
    freqs = np.fft.rfftfreq(segment.size, d=1.0 / sample_rate)
    spectrum[freqs > PITCH_LOWPASS_HZ] = 0.0
    low = np.fft.irfft(spectrum, n=segment.size)

    low = low - low.mean()          # 직류 성분 제거 (없으면 모든 lag가 비슷하게 겹쳐 보인다)
    energy = float(np.dot(low, low))
    if energy <= EPS:
        return 0.0

    # ── 2) 사람 목소리 음정 범위에 해당하는 밀기 거리(lag)만 검사 ──
    min_lag = max(1, int(sample_rate / PITCH_MAX_HZ))
    max_lag = min(low.size - 1, int(sample_rate / PITCH_MIN_HZ))
    if max_lag <= min_lag:
        return 0.0

    # 자기상관을 FFT로 한 번에 계산한다 (직접 곱하면 느리다)
    size = 1 << (2 * low.size - 1).bit_length()
    freq_domain = np.fft.rfft(low, n=size)
    autocorr = np.fft.irfft(freq_domain * np.conj(freq_domain), n=size)[: low.size]

    candidates = autocorr[min_lag : max_lag + 1]
    if candidates.size == 0:
        return 0.0
    # autocorr[0] 이 곧 전체 에너지라, 그것으로 나누면 0~1 범위가 된다
    return float(max(0.0, candidates.max() / (autocorr[0] + EPS)))


def compute_decay_ms(segment: np.ndarray, sample_rate: int,
                     frame_ms: float = 5.0, drop_db: float = 15.0) -> float:
    """소리가 정점 이후 얼마 만에 잦아드는지(ms).

    왜 필요한가 — 이것 없이는 **종이 구기는 소리를 절대 못 거른다.**
    종이 소리는 고음 비율·평탄도·영교차율이 박수와 거의 똑같이 나온다(실측 확인).
    유일한 차이가 '박수는 순식간에 끝나고 종이는 계속 이어진다'는 점이다.

    정점을 찍은 뒤 15dB 아래로 떨어지는 데 걸린 시간을 잰다.
    조각이 끝날 때까지 안 떨어지면 조각 길이를 그대로 돌려준다(= 아직 안 끝났다는 뜻).
    """
    if segment.size == 0:
        return 0.0

    frame_size = max(1, int(sample_rate * frame_ms / 1000))
    frame_count = segment.size // frame_size
    if frame_count < 2:
        return 0.0

    # 조각을 작은 프레임으로 잘라 각 프레임의 에너지를 구한다 = 소리의 '봉투'
    frames = segment[: frame_count * frame_size].reshape(frame_count, frame_size)
    envelope = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1))

    peak_index = int(np.argmax(envelope))
    peak_value = float(envelope[peak_index])
    if peak_value <= EPS:
        return 0.0

    floor = peak_value * (10 ** (-drop_db / 20))
    after_peak = envelope[peak_index:]
    below = np.flatnonzero(after_peak < floor)
    if below.size == 0:
        # 조각이 끝날 때까지 안 잦아들었다 = 계속 이어지는 소리
        return float((frame_count - peak_index) * frame_ms)
    return float(below[0] * frame_ms)


def compute_crest_factor(segment: np.ndarray) -> float:
    """최대 진폭 ÷ RMS. '얼마나 뾰족한가'.

    ⚠️ 판정에는 쓰지 않는다. 리미터(클리핑 가드)가 정확히 이 값을 깎아내리기 때문이다.
    리미터가 걸린 마이크에서는 박수도 이 값이 낮게 나온다.
    보정 화면에서 "이 마이크에 리미터가 걸려 있는 것 같다"를 알려주는 진단용으로만 쓴다.
    """
    if segment.size == 0:
        return 0.0
    rms = compute_rms(segment)
    if rms <= EPS:
        return 0.0
    return float(np.abs(segment).max() / rms)


def extract_event_features(segment: np.ndarray, sample_rate: int) -> EventFeatures:
    """소리 조각 하나에서 모든 이벤트 특징을 뽑는다."""
    return EventFeatures(
        high_freq_ratio=compute_high_freq_ratio(segment, sample_rate),
        flatness=compute_flatness(segment),
        zero_crossing_rate=compute_zero_crossing_rate(segment),
        harmonicity=compute_harmonicity(segment, sample_rate),
        decay_ms=compute_decay_ms(segment, sample_rate),
        crest_factor=compute_crest_factor(segment),
        peak=float(np.abs(segment).max()) if segment.size else 0.0,
    )
