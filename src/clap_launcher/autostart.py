"""Windows 시작 시 자동 실행 등록/해제.

왜 필요한가:
이 프로그램의 가치는 "자리에 앉아 잠금을 풀면 알아서 준비되는 것"이다.
그런데 정작 이 프로그램을 매번 손으로 켜야 한다면 앞뒤가 맞지 않는다.

왜 레지스트리인가:
  · 시작 프로그램 폴더에 바로가기(.lnk)를 만들려면 COM(win32com)이 필요하다 — 의존성이 는다
  · 작업 스케줄러는 관리자 권한을 요구하는 경우가 있다
  · HKEY_CURRENT_USER 의 Run 키는 **관리자 권한 없이** 쓸 수 있고, 지우기도 쉽다

⚠️ 등록되는 것은 '지금 이 프로그램을 실행한 방법'이다. 가상환경에서 개발 중이라면
   그 가상환경의 python 경로가 박힌다. 나중에 exe 로 배포하면(M6) exe 경로가 박힌다.
   가상환경을 지우면 등록만 남고 실행은 실패하므로, 그때는 다시 등록해야 한다.
"""

import sys
from pathlib import Path

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ClapDesk"           # 레지스트리에 남는 이름 (사용자가 작업 관리자에서 보게 된다)
# 예전 이름으로 등록해 둔 것. 앱 이름을 바꿨는데 이걸 그냥 두면
# **화면 토글은 '꺼짐'인데 로그인하면 실행되는** 유령 상태가 된다. 그래서 함께 정리한다.
LEGACY_VALUE_NAMES = ("ClappingSetup",)


def build_launch_command() -> str:
    """자동 시작에 등록할 명령줄을 만든다.

    경로에 공백이 있는 경우가 대부분이라(Program Files, 한글 사용자 폴더 등)
    **큰따옴표로 감싸는 것이 필수**다. 안 그러면 조용히 실행되지 않는다.

    ⚠️ `--minimized` 를 붙이는 이유: 로그인할 때마다 창이 튀어나오면 성가시다.
       트레이에 조용히 들어가 있다가 잠금을 풀 때 일하는 게 이 기능의 취지에 맞다.

    Returns:
        exe 로 묶였으면      : "C:/.../ClapDesk.exe" --minimized
        소스로 실행 중이면   : "C:/.../pythonw.exe" -m clap_launcher --minimized
    """
    executable = Path(sys.executable)

    if getattr(sys, "frozen", False):     # PyInstaller 로 만든 exe 안에서 실행 중
        return f'"{executable}" --minimized'

    # 개발 중: 콘솔 창이 뜨지 않도록 python.exe 대신 pythonw.exe 를 쓴다.
    # 로그인할 때마다 검은 콘솔 창이 뜨면 누구라도 이 기능을 꺼버린다.
    windowless = executable.with_name(executable.name.replace("python.exe", "pythonw.exe"))
    if windowless.is_file():
        executable = windowless
    return f'"{executable}" -m clap_launcher --minimized'


def _open_run_key(write: bool):
    """Run 키를 연다. Windows 가 아니면 None.

    쓰기 모드에서 CreateKeyEx 를 쓰는 이유: 이미 있으면 그냥 열고, 없으면 만들어 준다.
    (Run 키는 항상 존재하지만, 테스트에서 다른 키를 가리켜도 그대로 동작한다)
    """
    if sys.platform != "win32":
        return None
    import winreg

    try:
        if write:
            return winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0,
                                      winreg.KEY_SET_VALUE)
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ)
    except OSError:
        return None


def is_enabled() -> bool:
    """자동 실행이 등록되어 있는가.

    예전 이름으로 등록된 것도 '켜짐'으로 본다. 그래야 화면 토글이 실제 동작과 일치한다.
    (예전 이름이 남아 있으면 로그인할 때 실제로 실행된다)

    Returns:
        Windows 가 아니거나 읽지 못하면 False. (없는 기능은 '꺼짐'으로 보여주는 게 정직하다)
    """
    key = _open_run_key(write=False)
    if key is None:
        return False

    import winreg
    try:
        for name in (VALUE_NAME, *LEGACY_VALUE_NAMES):
            try:
                value, _type = winreg.QueryValueEx(key, name)
            except OSError:
                continue      # 이 이름으로는 등록 안 됨 — 다음 이름을 본다
            if value:
                return True
        return False
    finally:
        key.Close()


def _delete_values(key, names) -> None:
    """주어진 이름들을 지운다. 없으면 그냥 넘어간다."""
    import winreg

    for name in names:
        try:
            winreg.DeleteValue(key, name)
        except OSError:
            pass              # 원래 없었다 — 지울 것도 없다


def enable() -> bool:
    """자동 실행을 등록한다. 성공하면 True.

    예전 이름은 함께 지운다. 안 그러면 로그인할 때 두 번 실행된다.
    """
    key = _open_run_key(write=True)
    if key is None:
        return False

    import winreg
    try:
        _delete_values(key, LEGACY_VALUE_NAMES)
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, build_launch_command())
        return True
    except OSError:
        return False
    finally:
        key.Close()


def disable() -> bool:
    """자동 실행 등록을 지운다. 성공하면 True.

    이미 없는 경우에도 True 를 돌려준다. 사용자가 원한 결과('등록되어 있지 않음')는
    똑같이 이뤄졌기 때문이다. 예전 이름도 함께 지운다 —
    하나만 지우면 토글은 꺼졌는데 로그인하면 실행되는 유령 상태가 남는다.
    """
    key = _open_run_key(write=True)
    if key is None:
        return False

    try:
        _delete_values(key, (VALUE_NAME, *LEGACY_VALUE_NAMES))
    except OSError:
        return False
    finally:
        key.Close()
    return True


def set_enabled(enabled: bool) -> bool:
    """켜고 끄기를 한 번에. 화면의 토글이 이 함수를 부른다."""
    return enable() if enabled else disable()
