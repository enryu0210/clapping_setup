"""기기별 설정 저장 — 사용자가 UI에서 고른 마이크 등을 기억한다.

⚠️ apps.yaml 과 이 파일은 역할이 다르다. 헷갈리지 말 것.

  config/apps.yaml   : 사람이 손으로 편집하는 파일. 주석이 잔뜩 들어 있다.
                       프로그램이 이 파일을 덮어쓰면 주석이 전부 날아가므로 읽기만 한다.
  settings.json      : 프로그램이 저장하는 파일. UI에서 고른 마이크 같은 것.
                       사람이 볼 일이 거의 없고, 언제든 프로그램이 덮어쓴다.

저장 위치를 저장소 폴더가 아니라 %LOCALAPPDATA% 로 잡은 이유:
나중에 exe로 패키징하면 프로그램이 Program Files 같은 '쓰기 금지' 폴더에 설치된다.
그 옆에 설정을 쓰려고 하면 권한 오류가 난다. 사용자별 폴더에 두면 그 문제가 없다.
겸사겸사 '마이크 선택'은 기기마다 다른 값이라, 저장소에 들어가면 안 되는 정보이기도 하다.
"""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

APP_DIR_NAME = "ClappingSetup"
SETTINGS_ENV_VAR = "CLAP_LAUNCHER_SETTINGS"  # 테스트에서 저장 경로를 갈아끼우기 위한 통로


@dataclass
class Settings:
    """프로그램이 기억해야 하는 기기별 값들."""

    device: int | str | None = None   # 고른 마이크 (번호 또는 이름 일부)
    device_label: str = ""            # 화면에 보여줄 이름. 번호가 바뀌어도 사람이 알아보게
    setup_done: bool = False          # 마이크 선택을 한 번이라도 끝냈는가
    # 보정 결과(기준값). None이면 기본값을 쓴다.
    # 마이크마다 값이 다르므로 이것도 기기별 정보다 — 저장소가 아니라 여기에 둔다.
    detection: dict | None = None

    # ── 언제 마이크를 열 것인가 (자세한 배경은 listening.py 참고) ──
    auto_arm_on_unlock: bool = True   # 화면 잠금이 풀리면 자동으로 듣기 시작
    listen_timeout_min: float = 5.0   # 이 시간 동안 박수가 없으면 자동으로 멈춤 (0=무제한)

    # ── 트레이 상주 (자세한 배경은 ui/tray.py 참고) ──
    minimize_to_tray: bool = True     # 창을 닫으면 종료하지 않고 트레이로 내려간다
    tray_notice_shown: bool = False   # '트레이로 내려갔다'는 안내를 이미 보여줬는가
    # ⚠️ '시작 시 자동 실행'은 여기 없다. 그건 Windows 레지스트리가 진짜 상태이고,
    #    여기에 또 적으면 둘이 어긋났을 때 어느 쪽이 맞는지 알 수 없게 된다.
    #    (사용자가 작업 관리자에서 직접 끌 수도 있다) → autostart.is_enabled() 로 그때그때 읽는다

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        """모르는 키는 무시하고, 없는 키는 기본값으로 채운다.

        이렇게 해두면 나중에 설정 항목이 늘거나 줄어도 예전 파일 때문에 프로그램이 죽지 않는다.
        """
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


def settings_path() -> Path:
    """설정 파일의 전체 경로. 환경변수로 덮어쓸 수 있다(테스트용)."""
    override = os.environ.get(SETTINGS_ENV_VAR)
    if override:
        return Path(override)

    # LOCALAPPDATA 는 Windows에만 있다. 없으면 홈 폴더로 물러선다.
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / APP_DIR_NAME / "settings.json"


def load_settings() -> Settings:
    """설정을 읽는다. 파일이 없거나 깨져 있으면 기본값을 돌려준다.

    설정 파일이 깨졌다고 프로그램이 죽으면 사용자는 손쓸 방법이 없다.
    (그 파일을 어떻게 지우는지도 모른다) 조용히 기본값으로 시작하는 편이 낫다.
    """
    path = settings_path()
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return Settings()                      # 첫 실행 — 정상 상황이다
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return Settings()                      # 깨졌거나 못 읽음 — 처음부터 다시 고르게 한다

    if not isinstance(data, dict):
        return Settings()
    return Settings.from_dict(data)


def save_settings(settings: Settings) -> None:
    """설정을 저장한다. 저장 도중 문제가 생겨도 기존 파일이 깨지지 않게 원자적으로 쓴다.

    그냥 열어서 쓰는 도중에 프로그램이 죽으면 파일이 반만 남아 다음 실행 때 못 읽는다.
    임시 파일에 완전히 쓴 다음 이름을 바꿔치기하면 '완전한 예전 파일'이거나
    '완전한 새 파일'이거나 둘 중 하나만 존재하게 된다.
    """
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # 같은 폴더에 임시 파일을 만든다(다른 드라이브면 os.replace 가 실패할 수 있으므로)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)   # 이름 바꿔치기는 원자적 연산이다
    except BaseException:
        # 실패하면 임시 파일 찌꺼기를 남기지 않는다
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
