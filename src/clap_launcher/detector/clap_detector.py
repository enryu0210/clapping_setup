"""[3] 박수 2회(짝짝) 판정 상태기계.

판정 4단계 (자세한 근거는 docs/ARCHITECTURE.md 3장):
  1) 크기   : 최근 배경 소음 평균 × sensitivity 보다 클 것
  2) 지속   : 큰 상태가 120ms 안에 끝날 것        -> 음악·대화 배제
  3) 주파수 : 고음 비율 > high_freq_ratio          -> 문 닫는 '쿵' 배제
  4) 간격   : 두 피크 간격이 150~800ms 일 것       -> 한 번뿐인 소리 배제

⚠️ 설계 포인트: 현재 시각을 내부에서 time.time() 으로 읽지 않고 인자로 받는다.
   그래야 테스트에서 시간을 마음대로 조작해 "1.5초 뒤 두 번째 박수" 같은 상황을
   기다리지 않고 즉시 검증할 수 있다.

TODO(M2~M3): 실제 판정 구현.
"""

from enum import Enum, auto

MAX_PEAK_DURATION_MS = 120   # 이보다 오래 지속되면 박수가 아니라 '계속 나는 소리'
REFRACTORY_MS = 100          # 첫 박수의 잔향을 두 번째 박수로 세지 않기 위한 불응기
NOISE_WINDOW_SEC = 3.0       # 배경 소음 평균을 낼 구간


class State(Enum):
    """감지기의 현재 상태."""

    IDLE = auto()      # 대기 — 첫 박수를 기다림
    ARMED = auto()     # 첫 박수를 들음 — 제한 시간 안에 두 번째를 기다림
    COOLDOWN = auto()  # 방금 발동함 — 잠시 아무것도 감지하지 않음


class ClapDetector:
    """조각의 특징값을 순서대로 받아 '짝짝'인지 판정한다."""

    def __init__(self, config) -> None:
        self.config = config          # DetectionConfig
        self.state = State.IDLE

    def feed(self, rms: float, high_freq_ratio: float, now: float) -> bool:
        """조각 하나를 넣는다. '짝짝'이 완성된 순간에만 True 를 반환한다.

        Args:
            rms: 이 조각의 소리 크기
            high_freq_ratio: 이 조각의 고음 비율
            now: 현재 시각(초). 테스트에서 조작할 수 있도록 밖에서 받는다.
        """
        raise NotImplementedError("TODO(M3): 4단계 판정 + 상태 전이 구현")
