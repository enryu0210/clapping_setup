"""[0] 설정 파일(config/apps.yaml) 읽기와 검증.

여기서 잘못된 설정을 전부 걸러내는 이유:
프로그램이 한참 돌다가 박수를 친 순간에 "경로가 없다"고 죽으면 원인을 찾기 어렵습니다.
시작할 때 한 번에 검사하고 친절한 메시지로 알려주는 편이 훨씬 낫습니다.

⚠️ 이 파일은 **읽기만** 합니다. 프로그램이 apps.yaml 을 덮어쓰면 그 안의 설명 주석이
   전부 날아갑니다. 프로그램이 저장해야 하는 값은 settings.py(settings.json)로 갑니다.
"""

import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .settings import APP_DIR_NAME, LEGACY_APP_DIR_NAME

CONFIG_ENV_VAR = "CLAP_LAUNCHER_CONFIG"   # 테스트·고급 사용자가 경로를 갈아끼우는 통로
CONFIG_FILE_NAME = "apps.yaml"
EXAMPLE_FILE_NAME = "apps.example.yaml"

VALID_APP_TYPES = ("exe", "url", "folder", "store")

# detection 항목 중 정수여야 하는 것들 (나머지는 실수)
_INT_DETECTION_FIELDS = frozenset({"min_interval_ms", "max_interval_ms"})


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
        (사람이 편집하는 apps.yaml 쪽은 오타를 잡아줘야 하므로 아래 _parse_detection 에서
         따로, 더 엄격하게 검사한다)
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
    # 이미 켜져 있으면 건너뛸지. 기본값이 True 인 이유: 아침에 켠 뒤 점심때 또 박수를
    # 쳤다고 같은 창이 하나 더 뜨는 건 대부분의 경우 원하는 동작이 아니다.
    # 브라우저처럼 창을 하나 더 띄우고 싶은 항목만 false 로 두면 된다. (exe 에만 해당)
    skip_if_running: bool = True


@dataclass
class Config:
    detection: DetectionConfig
    apps: list[AppEntry]
    audio: AudioConfig = field(default_factory=AudioConfig)

    @property
    def enabled_apps(self) -> list[AppEntry]:
        """실제로 실행될 항목만. enabled: false 는 여기서 빠진다."""
        return [app for app in self.apps if app.enabled]


class ConfigError(Exception):
    """설정 파일이 없거나 형식이 잘못됐을 때. 메시지에 해결 방법까지 담는다."""


# ── 설정 파일 찾기 ────────────────────────────────────────────

def _app_dir() -> Path:
    """프로그램의 기준 폴더.

    ⚠️ 절대 경로를 코드에 박으면 안 된다. 기기마다 저장소 위치가 다르고,
       나중에 exe로 묶으면 위치가 또 달라진다. 그래서 그때그때 계산한다.
    """
    if getattr(sys, "frozen", False):            # PyInstaller 로 만든 exe 안에서 실행 중
        return Path(sys.executable).resolve().parent
    # src/clap_launcher/config.py → [0]=clap_launcher, [1]=src, [2]=저장소 루트
    return Path(__file__).resolve().parents[2]


def config_search_paths() -> list[Path]:
    """설정 파일을 찾아볼 곳들. 앞에 있는 것이 우선한다.

    1. 환경변수 CLAP_LAUNCHER_CONFIG — 테스트와 '다른 설정으로 잠깐 돌려보기'용
    2. 프로그램 폴더의 config/apps.yaml — 개발 중에 실제로 편집하는 파일
    3. %LOCALAPPDATA%\\ClapDesk\\apps.yaml — exe를 쓰기 금지 폴더에 설치했을 때의 대피처
    4. 예전 이름(ClappingSetup) 폴더 — 이름을 바꾸기 전에 저장해 둔 설정을 잃지 않기 위해
    """
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return [Path(override)]

    paths = [_app_dir() / "config" / CONFIG_FILE_NAME]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
        paths.append(base / APP_DIR_NAME / CONFIG_FILE_NAME)
        paths.append(base / LEGACY_APP_DIR_NAME / CONFIG_FILE_NAME)
    return paths


def find_config_path() -> Path | None:
    """실제로 존재하는 설정 파일의 경로. 하나도 없으면 None."""
    for path in config_search_paths():
        if path.is_file():
            return path
    return None


def _missing_config_message(searched: list[Path]) -> str:
    """설정 파일이 없을 때의 안내문. '어디를 찾아봤고 무엇을 하면 되는지'까지 적는다."""
    where = "\n".join(f"    - {path}" for path in searched)
    return (
        "설정 파일을 찾지 못했습니다.\n"
        f"  찾아본 곳:\n{where}\n"
        "  예시 파일을 복사한 뒤 본인 PC의 경로로 고쳐주세요:\n"
        f"    copy config\\{EXAMPLE_FILE_NAME} config\\{CONFIG_FILE_NAME}"
    )


# ── 파싱 ─────────────────────────────────────────────────────

def load_config(path: str | Path | None = None) -> Config:
    """YAML 파일을 읽어 Config 로 만든다.

    Args:
        path: 읽을 파일. None이면 config_search_paths() 에서 자동으로 찾는다.

    실패 시 ConfigError 를 던지며, 메시지에는 '무엇이 잘못됐고 어떻게 고치는지'를 담는다.
      - 파일 없음    -> "apps.example.yaml 을 apps.yaml 로 복사하세요"
      - 문법 오류    -> 몇 번째 줄이 문제인지
      - 필수 키 누락 -> 몇 번째 항목의 어떤 키가 빠졌는지
    """
    if path is None:
        found = find_config_path()
        if found is None:
            raise ConfigError(_missing_config_message(config_search_paths()))
        target = found
    else:
        target = Path(path)

    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(_missing_config_message([target])) from None
    except UnicodeDecodeError:
        raise ConfigError(
            f"설정 파일을 UTF-8로 읽지 못했습니다: {target}\n"
            "  메모장에서 '다른 이름으로 저장' → 인코딩을 UTF-8 로 바꿔 저장해 주세요."
        ) from None
    except OSError as exc:
        raise ConfigError(f"설정 파일을 열지 못했습니다: {target}\n  {exc}") from exc

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"설정 파일의 YAML 문법이 잘못됐습니다: {target}\n"
                          f"  {_yaml_error_detail(exc)}") from exc

    if raw is None:            # 파일이 비었거나 주석만 있는 경우
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(
            f"설정 파일의 최상위는 'audio:', 'detection:', 'apps:' 같은 항목 목록이어야 합니다: {target}"
        )

    return Config(
        detection=_parse_detection(raw.get("detection")),
        apps=_parse_apps(raw.get("apps")),
        audio=_parse_audio(raw.get("audio")),
    )


def _yaml_error_detail(exc: yaml.YAMLError) -> str:
    """YAML 오류에서 '몇 번째 줄이 문제인지'를 뽑아낸다.

    PyYAML 의 오류를 그대로 보여주면 사용자는 어디를 고쳐야 할지 알 수 없다.
    (줄 번호가 0부터 세어져 있어서 +1 해야 편집기의 줄 번호와 맞는다)
    """
    mark = getattr(exc, "problem_mark", None)
    problem = getattr(exc, "problem", None) or str(exc)
    if mark is None:
        return problem
    return (f"{mark.line + 1}번째 줄 근처: {problem}\n"
            "  들여쓰기가 어긋났거나, 경로에 따옴표를 안 씌운 경우가 대부분입니다.")


def _parse_audio(raw) -> AudioConfig:
    """audio: 항목. 비어 있으면 Windows 기본 장치를 쓴다."""
    if raw is None:
        return AudioConfig()
    if not isinstance(raw, dict):
        raise ConfigError("audio: 항목은 'device:' 같은 하위 항목을 가져야 합니다.")

    device = raw.get("device")
    if device is None or isinstance(device, str):
        return AudioConfig(device=device)
    # bool 은 파이썬에서 int 취급이라 먼저 걸러야 한다 (device: true 를 1번 장치로 읽으면 곤란)
    if isinstance(device, bool) or not isinstance(device, int):
        raise ConfigError(
            f"audio.device 는 장치 번호(숫자)나 이름 일부(문자열)여야 합니다. 지금 값: {device!r}\n"
            "  목록은 'python -m clap_launcher --list-devices' 로 볼 수 있습니다."
        )
    return AudioConfig(device=device)


def _parse_detection(raw) -> DetectionConfig:
    """detection: 항목. 생략하면 기본 기준값을 쓴다.

    ⚠️ 여기는 settings.json 쪽(from_dict)과 달리 **모르는 항목을 오류로 처리한다.**
       사람이 손으로 적는 파일이라, 오타 난 항목을 조용히 무시하면
       "설정을 바꿨는데 왜 안 먹지?"로 몇 시간을 날리게 된다.
    """
    if raw is None:
        return DetectionConfig()
    if not isinstance(raw, dict):
        raise ConfigError("detection: 항목은 'onset_rise_db: 8.0' 같은 하위 항목을 가져야 합니다.")

    known = DetectionConfig.__dataclass_fields__
    values: dict[str, float | int] = {}
    for key, value in raw.items():
        if key not in known:
            raise ConfigError(
                f"detection 에 모르는 항목이 있습니다: '{key}' (오타일 수 있습니다)\n"
                f"  쓸 수 있는 항목: {', '.join(known)}"
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"detection.{key} 는 숫자여야 합니다. 지금 값: {value!r}")
        if value < 0:
            raise ConfigError(f"detection.{key} 는 0 이상이어야 합니다. 지금 값: {value}")
        values[key] = int(value) if key in _INT_DETECTION_FIELDS else float(value)

    config = DetectionConfig(**values)
    _check_min_max(config)
    return config


def _check_min_max(config: DetectionConfig) -> None:
    """하한이 상한보다 큰 조합을 막는다.

    이걸 통과시키면 어떤 소리도 통과할 수 없는 설정이 되어 "박수를 쳐도 반응이 없다"가
    된다. 게다가 로그에는 그냥 '걸러짐'으로만 찍혀서 원인을 찾기가 매우 어렵다.
    """
    pairs = [
        ("min_flatness", "max_flatness"),
        ("min_decay_ms", "max_decay_ms"),
        ("min_interval_ms", "max_interval_ms"),
    ]
    for low_key, high_key in pairs:
        low, high = getattr(config, low_key), getattr(config, high_key)
        if low >= high:
            raise ConfigError(
                f"detection.{low_key}({low}) 가 {high_key}({high}) 보다 크거나 같습니다.\n"
                "  이렇게 두면 어떤 소리도 통과하지 못해 박수를 쳐도 반응하지 않습니다."
            )


def _parse_apps(raw) -> list[AppEntry]:
    """apps: 항목. 목록 순서대로 실행된다."""
    if raw is None:
        return []          # 아직 등록을 안 한 상태 — 오류는 아니다. 실행할 때 안내한다.
    if not isinstance(raw, list):
        raise ConfigError(
            "apps: 항목은 '- name: ...' 로 시작하는 목록이어야 합니다.\n"
            "  각 줄 앞의 '-' 를 빠뜨리지 않았는지 확인해 주세요."
        )
    return [_parse_app_entry(item, order) for order, item in enumerate(raw, start=1)]


def _parse_app_entry(raw, order: int) -> AppEntry:
    """apps 목록의 항목 하나. 오류 메시지에 '몇 번째 항목'인지를 항상 붙인다."""
    where = f"apps 의 {order}번째 항목"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}이 잘못됐습니다: 'name:', 'path:' 같은 하위 항목이 필요합니다.")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"{where}에 name(표시할 이름)이 없습니다.")
    name = name.strip()

    app_type = raw.get("type", "exe")
    if app_type not in VALID_APP_TYPES:
        raise ConfigError(
            f"'{name}' 의 type 이 잘못됐습니다: {app_type!r}\n"
            f"  쓸 수 있는 값: {', '.join(VALID_APP_TYPES)}"
        )

    path = raw.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ConfigError(
            f"'{name}' 에 path 가 없습니다. (type: {app_type} 이므로 "
            f"{_path_hint(app_type)}를 적어주세요)"
        )

    return AppEntry(
        name=name,
        path=path.strip(),
        type=app_type,
        args=_parse_args(raw.get("args"), name),
        delay=_parse_delay(raw.get("delay"), name),
        enabled=_parse_flag(raw.get("enabled"), name, "enabled", default=True),
        skip_if_running=_parse_flag(raw.get("skip_if_running"), name,
                                    "skip_if_running", default=True),
    )


def _path_hint(app_type: str) -> str:
    return {
        "exe": "실행파일의 전체 경로",
        "url": "웹 주소",
        "folder": "폴더 경로",
        "store": "스토어 앱 ID",
    }[app_type]


def _parse_args(raw, name: str) -> list[str]:
    """args: 실행 인자. 하나만 쓸 때 목록을 빼먹기 쉬워서 문자열도 받아준다."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]        # args: "F:/dev" 처럼 적어도 동작하게 (흔한 실수)
    if not isinstance(raw, list):
        raise ConfigError(f"'{name}' 의 args 는 목록이어야 합니다. 예: args: [\"F:/dev\"]")
    # 숫자를 적는 경우가 있어 문자열로 바꿔준다 (subprocess 는 문자열만 받는다)
    return [str(item) for item in raw]


def _parse_delay(raw, name: str) -> float:
    """delay: 이 항목을 실행한 뒤 다음 항목까지 기다릴 초."""
    if raw is None:
        return 0.0
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ConfigError(f"'{name}' 의 delay 는 초 단위 숫자여야 합니다. 지금 값: {raw!r}")
    if raw < 0:
        raise ConfigError(f"'{name}' 의 delay 는 0 이상이어야 합니다. 지금 값: {raw}")
    return float(raw)


def _parse_flag(raw, name: str, key: str, default: bool) -> bool:
    """true/false 항목 하나. enabled, skip_if_running 처럼 같은 검사가 반복돼서 묶었다."""
    if raw is None:
        return default
    if not isinstance(raw, bool):
        raise ConfigError(f"'{name}' 의 {key} 는 true 또는 false 여야 합니다. 지금 값: {raw!r}")
    return raw


# ── 저장 ─────────────────────────────────────────────────
#
# ⚠️ 원래 이 파일은 '읽기 전용'이었다. 프로그램이 apps.yaml 을 덮어쓰면 사용자가 적어둔
#    설명 주석이 날아가기 때문이다. 그런데 프로그램 목록을 화면에서 편집할 수 있게 되면서
#    어딘가에는 저장해야 했다. 선택지는 두 가지였다.
#
#      (가) 목록을 settings.json 에 따로 저장한다  → 설정이 두 군데로 갈라진다.
#           손으로 apps.yaml 을 고쳤는데 화면이 무시하는 상황이 생긴다.
#      (나) apps.yaml 을 다시 쓴다                → 주석이 날아간다.
#
#    (나)를 골랐다. '설정 파일은 하나'라는 게 훨씬 중요하고, 주석 문제는
#    **직전 파일을 .bak 으로 남기는 것**으로 되돌릴 수 있게 했다.
#    대신 화면에도 이 사실을 분명히 적어둔다.

BACKUP_SUFFIX = ".bak"

_FILE_HEADER = """\
# ================================================================
#  ClapDesk 설정
#
#  ⚠️ 이 파일은 프로그램의 [프로그램 설정] 화면에서 저장할 때 **다시 작성**됩니다.
#     직접 적어둔 주석은 그때 사라집니다. 직전 내용은 apps.yaml.bak 에 남습니다.
#     손으로만 관리하고 싶다면 화면에서 저장하지 말고 이 파일만 편집하세요.
#
#  자세한 설명은 docs/CONFIG.md 참고.
# ================================================================
"""


def dump_config_text(config: Config) -> str:
    """Config 를 apps.yaml 파일 내용(문자열)으로 만든다.

    파일을 건드리지 않는 순수 함수라 테스트하기 쉽다.
    항목은 **기본값과 다른 것만** 적는다. 전부 적으면 읽기 어려워지기 때문이다.
    """
    parts = [_FILE_HEADER]

    # ── audio ──
    if config.audio.device is None:
        parts.append("\n# 쓸 마이크 (비워두면 Windows 기본 장치. 보통은 화면에서 고른다)\n"
                     "audio:\n  device:\n")
    else:
        parts.append("\n# 쓸 마이크\n" + _yaml_block({"audio": {"device": config.audio.device}}))

    # ── detection ──
    parts.append("\n# 박수 감지 기준값 — 보통은 [박수 보정] 버튼을 쓰세요.\n"
                 "# 각 값의 근거는 docs/DETECTION.md 참고.\n")
    parts.append(_yaml_block({"detection": config.detection.to_dict()}))

    # ── apps ──
    parts.append("\n# 박수 치면 실행할 것들 (위에서 아래 순서대로 실행)\n")
    if not config.apps:
        parts.append("apps: []\n")
    else:
        parts.append(_yaml_block({"apps": [_app_to_dict(app) for app in config.apps]}))
    return "".join(parts)


def _app_to_dict(app: AppEntry) -> dict:
    """항목 하나를 사전으로. 기본값인 항목은 빼서 파일을 짧게 유지한다."""
    data = {"name": app.name, "type": app.type, "path": app.path}
    if app.args:
        data["args"] = list(app.args)
    if app.delay:
        data["delay"] = app.delay
    if not app.enabled:
        data["enabled"] = False
    if not app.skip_if_running:
        data["skip_if_running"] = False
    return data


def _yaml_block(data: dict) -> str:
    """사전 하나를 YAML 조각으로. 한글이 깨지지 않게, 적은 순서 그대로 쓴다."""
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False,
                          default_flow_style=False, width=1000)


def save_config(config: Config, path: str | Path | None = None) -> Path:
    """설정을 파일에 쓴다.

    Args:
        path: 저장할 위치. None이면 지금 읽고 있는 파일, 그것도 없으면 첫 번째 후보 경로.

    Returns:
        실제로 저장한 경로.

    Raises:
        ConfigError: 어디에도 쓸 수 없을 때 (권한 문제 등). 메시지에 이유를 담는다.
    """
    text = dump_config_text(config)

    if path is not None:
        return _write_config_file(Path(path), text)

    # 후보를 순서대로 시도한다. exe를 '쓰기 금지' 폴더에 설치하면 첫 후보가 실패하는데,
    # 그때 조용히 포기하지 않고 사용자 폴더(%LOCALAPPDATA%)로 물러선다.
    candidates = [p for p in config_search_paths() if p.is_file()] or config_search_paths()
    problems = []
    for candidate in candidates:
        try:
            return _write_config_file(candidate, text)
        except OSError as exc:
            problems.append(f"  - {candidate}: {exc}")

    raise ConfigError("설정을 저장할 수 없습니다. 아래 위치에 모두 실패했습니다.\n"
                      + "\n".join(problems))


def _write_config_file(path: Path, text: str) -> Path:
    """실제 쓰기. 직전 파일을 백업하고, 도중에 죽어도 파일이 반토막 나지 않게 한다."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # 직전 내용을 남긴다. 화면에서 실수로 저장했을 때 되돌릴 유일한 방법이다.
    if path.is_file():
        try:
            backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass      # 백업 실패가 저장 자체를 막을 이유는 없다

    # 임시 파일에 다 쓴 뒤 이름을 바꿔치기한다 (settings.py 와 같은 방식)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path
