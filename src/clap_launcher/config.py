"""[0] 설정 파일(config/apps.yaml) 읽기와 검증.

여기서 잘못된 설정을 전부 걸러내는 이유:
프로그램이 한참 돌다가 박수를 친 순간에 "경로가 없다"고 죽으면 원인을 찾기 어렵습니다.
시작할 때 한 번에 검사하고 친절한 메시지로 알려주는 편이 훨씬 낫습니다.

TODO(M4): 실제 파싱 구현.
"""

from dataclasses import asdict, dataclass, field


@dataclass
class DetectionConfig:
    """박수 감지 기준값.

    ⚠️ 여기 있는 값들은 전부 '비율'이거나 '변화량'이다. 절대 음량 기준이 하나도 없다.
    리미터(클리핑 가드)가 걸린 마이크에서도 값이 흔들리지 않게 하기 위해서다.
    각 값을 어떻게 정했는지는 docs/DETECTION.md 참고. (합성 신호로 실측해서 정했다)
    """

    # ── 1단계: "뭔가 시작됐다" 판단 ──
    onset_rise_db: float = 8.0       # 고음 에너지가 배경 대비 몇 dB 뛰어야 하는지

    # ── 2단계: "그게 박수인가" 판단 ──
    min_high_freq_ratio: float = 0.55  # 고음 비율 하한 (문 닫는 소리 배제. 박수 실측 0.97)
    min_flatness: float = 0.12         # 잡음스러움 하한 (음정 있는 소리 배제. 박수 0.30)
    max_flatness: float = 0.50         # 잡음스러움 상한 (**키보드 배제.** 아래 설명 참고)
    min_zero_crossing_rate: float = 0.35   # 날카로움 하한 (둔탁한 소리 배제. 박수 0.58)
    max_harmonicity: float = 0.55      # 음정 상한 (**기침·말소리 배제.** 기침 실측 0.89)
    max_decay_ms: float = 60.0         # 소리 길이 상한 (**종이·음악 배제.** 박수 25ms, 종이 110ms)
    min_decay_ms: float = 14.0         # 소리 길이 하한 (**키보드 배제.** 박수 26ms, 키보드 10ms)

    # ── 3단계: "짝-짝인가" 판단 ──
    min_interval_ms: int = 150       # 두 박수 사이 최소 간격 (잔향을 두 번으로 세지 않기 위함)
    max_interval_ms: int = 800       # 두 박수 사이 최대 간격
    cooldown_sec: float = 5.0        # 발동 후 재감지 금지 시간

    @classmethod
    def for_calibration(cls) -> "DetectionConfig":
        """보정할 때 쓰는 '느슨하지만 완전히 열려 있지는 않은' 설정.

        딜레마가 있다.
        - 기본 기준값 그대로 쓰면: 기준이 안 맞는 마이크에서 박수가 전부 걸러져
          정작 보정이 필요한 사람이 보정을 못 한다.
        - 조건을 완전히 열면: 에어컨 소리·의자 삐걱임까지 '박수'로 수집돼
          엉터리 기준값이 저장된다. (실제로 그런 일이 관찰됐다)

        그래서 **어떤 마이크의 박수라도 통과하지만, 명백히 박수가 아닌 것은 막는**
        넉넉한 울타리만 남긴다. 여기 있는 값들은 판별용이 아니라 '쓰레기 거르개'다.
        """
        return cls(
            min_high_freq_ratio=0.15,     # 완전한 저음 덩어리(냉장고·발소리) 배제
            min_flatness=0.0,             # 마이크마다 편차가 커서 열어둔다
            max_flatness=1.0,
            min_zero_crossing_rate=0.05,  # 웅웅거리는 소리 배제
            max_harmonicity=0.75,         # 명백한 말소리(0.9+) 배제
            max_decay_ms=200.0,           # 명백히 긴 소리 배제
            min_decay_ms=0.0,             # 짧은 소리도 일단 관찰한다 (그게 잡음 샘플이 된다)
            cooldown_sec=0.0,
        )

    def to_dict(self) -> dict:
        """보정 결과를 settings.json 에 저장하기 위해 사전으로 바꾼다."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DetectionConfig":
        """저장된 값을 되살린다. 모르는 항목은 무시하고, 빠진 항목은 기본값으로 채운다.

        이렇게 해두면 나중에 기준값 항목이 늘거나 줄어도 예전 보정 파일 때문에 죽지 않는다.
        """
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


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
