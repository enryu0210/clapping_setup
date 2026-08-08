"""[1] 마이크 입력 — sounddevice 로 소리 조각(frame)을 계속 읽어온다.

설정값 근거:
  - 16000Hz : 박수 판별에 필요한 고음(2~8kHz)까지 담기면서 계산량이 가볍다.
  - 모노    : 방향 정보는 필요 없다.
  - 160샘플(10ms) : 박수는 50ms 안에 끝나므로 조각이 크면 순간 피크가 평균에 묻힌다.

TODO(M1): 실제 스트림 구현.
"""

SAMPLE_RATE = 16000   # Hz
CHANNELS = 1          # 모노
BLOCK_SIZE = 160      # 샘플 수 = 10ms


class AudioDeviceError(Exception):
    """마이크가 없거나 권한이 없을 때. 원인과 해결 방법을 메시지에 담는다."""


class AudioListener:
    """마이크 스트림을 열고 조각을 하나씩 넘겨주는 객체.

    다른 앱(화상회의 등)과 동시에 쓸 수 있도록 반드시 '공유 모드'로 연다.
    독점 모드로 열면 회의 중 마이크를 빼앗는 문제가 생긴다.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, block_size: int = BLOCK_SIZE) -> None:
        self.sample_rate = sample_rate
        self.block_size = block_size

    def __enter__(self) -> "AudioListener":
        raise NotImplementedError("TODO(M1): sounddevice.InputStream 열기")

    def __exit__(self, *exc_info: object) -> None:
        """예외로 빠져나가도 스트림이 확실히 닫히도록 컨텍스트 매니저로 만든다."""
        raise NotImplementedError("TODO(M1): 스트림 정리")

    def frames(self):
        """조각을 하나씩 내주는 제너레이터. 각 조각은 numpy float32 배열."""
        raise NotImplementedError("TODO(M1): 큐에서 꺼내 yield")
