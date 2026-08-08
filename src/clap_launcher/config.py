"""[0] 설정 파일(config/apps.yaml) 읽기와 검증.

여기서 잘못된 설정을 전부 걸러내는 이유:
프로그램이 한참 돌다가 박수를 친 순간에 "경로가 없다"고 죽으면 원인을 찾기 어렵습니다.
시작할 때 한 번에 검사하고 친절한 메시지로 알려주는 편이 훨씬 낫습니다.

TODO(M4): 실제 파싱 구현.
"""

from dataclasses import dataclass, field


@dataclass
class DetectionConfig:
    """박수 감지 민감도. 각 값의 의미는 docs/CONFIG.md 4장 참고."""

    sensitivity: float = 6.0        # 배경 소음 대비 몇 배 커야 피크로 볼지
    min_interval_ms: int = 150      # 두 박수 사이 최소 간격 (잔향을 두 번으로 세지 않기 위함)
    max_interval_ms: int = 800      # 두 박수 사이 최대 간격
    high_freq_ratio: float = 0.4    # 고음 비율 하한 (저음 충격음 배제)
    cooldown_sec: float = 5.0       # 발동 후 재감지 금지 시간


@dataclass
class AudioConfig:
    """마이크 선택.

    왜 설정으로 빼는가 (M1에서 실제로 겪은 문제):
    PC에 오디오 인터페이스나 Elgato Wave Link 같은 가상 장치가 깔려 있으면
    Windows 기본 입력 장치가 '가상 장치'로 잡힌다. 그 앱이 꺼져 있으면 무음만 들어와서
    "박수를 쳐도 반응이 없다"가 된다. 사용자가 직접 고를 수 있어야 한다.
    """

    device: int | str | None = None   # 장치 번호 또는 이름 일부. None이면 Windows 기본값


@dataclass
class AppEntry:
    """박수 감지 시 실행할 대상 하나."""

    name: str                              # 로그에 표시할 이름
    path: str                              # 실행 경로 / URL / 폴더
    type: str = "exe"                      # exe | url | folder | store
    args: list[str] = field(default_factory=list)
    delay: float = 0.0                     # 실행 후 다음 항목까지 대기 초
    enabled: bool = True                   # false면 건너뜀 (지우지 않고 잠깐 끄기용)


@dataclass
class Config:
    detection: DetectionConfig
    apps: list[AppEntry]
    audio: AudioConfig = field(default_factory=AudioConfig)


class ConfigError(Exception):
    """설정 파일이 없거나 형식이 잘못됐을 때. 메시지에 해결 방법까지 담는다."""


def load_config(path: str) -> Config:
    """YAML 파일을 읽어 Config 로 만든다.

    실패 시 ConfigError 를 던지며, 메시지에는 '무엇이 잘못됐고 어떻게 고치는지'를 담는다.
      - 파일 없음  -> "config/apps.example.yaml 을 apps.yaml 로 복사하세요"
      - 문법 오류  -> 몇 번째 줄이 문제인지
      - 필수 키 누락 -> 어떤 항목의 어떤 키가 빠졌는지
    """
    raise NotImplementedError("TODO(M4): PyYAML 로 파싱 + 검증 구현")
