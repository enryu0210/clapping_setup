"""[2] 특징 추출 — 소리 조각을 숫자 몇 개로 요약한다.

  rms             : 소리 크기 (얼마나 큰가)              ← M1에서 구현
  high_freq_ratio : 2kHz 이상이 차지하는 비율 (얼마나 날카로운가)  ← M2에서 구현

이 두 숫자만으로 박수/말소리/충격음을 구분할 수 있다는 것이 이 프로젝트의 전제다.
상태를 갖지 않는 순수 함수로 두어 테스트하기 쉽게 만든다(가짜 사인파를 넣어 검증).
"""

import math

import numpy as np

HIGH_FREQ_CUTOFF_HZ = 2000  # 이 위쪽을 '고음'으로 본다. 박수의 특징 대역.
SILENCE_DBFS = -120.0       # 완전한 무음을 표시할 때 쓰는 하한값 (log(0) = -무한대 방지)


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


def compute_high_freq_ratio(frame: np.ndarray, sample_rate: int) -> float:
    """전체 에너지 대비 2kHz 이상 에너지 비율 (0.0~1.0).

    왜 필요한가: 문 닫는 소리 '쿵'은 박수만큼 크지만 저음이라 이 값이 낮다.
    음량만 보면 절대 못 거르는 오탐을 여기서 걸러낸다.
    """
    raise NotImplementedError("TODO(M2): np.fft.rfft 로 대역별 에너지 계산")
