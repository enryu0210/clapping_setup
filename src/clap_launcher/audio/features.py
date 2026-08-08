"""[2] 특징 추출 — 소리 조각을 숫자 2개로 요약한다.

  rms             : 소리 크기 (얼마나 큰가)
  high_freq_ratio : 전체 에너지 중 2kHz 이상이 차지하는 비율 (얼마나 날카로운가)

이 두 숫자만으로 박수/말소리/충격음을 구분할 수 있다는 것이 이 프로젝트의 전제다.
상태를 갖지 않는 순수 함수로 두어 테스트하기 쉽게 만든다(가짜 사인파를 넣어 검증).

TODO(M2): 실제 계산 구현.
"""

HIGH_FREQ_CUTOFF_HZ = 2000  # 이 위쪽을 '고음'으로 본다. 박수의 특징 대역.


def compute_rms(frame) -> float:
    """조각의 실효값(RMS). 사람이 느끼는 '소리 크기'에 가장 가까운 지표."""
    raise NotImplementedError("TODO(M2): sqrt(mean(frame**2))")


def compute_high_freq_ratio(frame, sample_rate: int) -> float:
    """전체 에너지 대비 2kHz 이상 에너지 비율 (0.0~1.0).

    왜 필요한가: 문 닫는 소리 '쿵'은 박수만큼 크지만 저음이라 이 값이 낮다.
    음량만 보면 절대 못 거르는 오탐을 여기서 걸러낸다.
    """
    raise NotImplementedError("TODO(M2): np.fft.rfft 로 대역별 에너지 계산")
