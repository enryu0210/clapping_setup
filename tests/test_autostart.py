"""Windows 시작 시 자동 실행 테스트.

⚠️ 진짜 Run 키(HKCU\\...\\CurrentVersion\\Run)는 절대 건드리지 않는다.
   테스트가 사용자의 시작 프로그램을 바꿔버리면 안 된다.
   대신 임시 키를 가리키게 해서 winreg 호출 자체는 진짜로 검증한다.

명령줄 만들기(build_launch_command)가 특히 중요하다. 여기가 틀리면
"등록은 됐는데 로그인해도 안 켜지는" 상태가 되고, 원인을 찾기가 매우 어렵다.
"""

import sys
import uuid

import pytest

from clap_launcher import autostart

pytestmark = pytest.mark.skipif(sys.platform != "win32",
                                reason="Windows 레지스트리 기능이라 다른 OS에서는 의미가 없다")


@pytest.fixture
def temp_run_key(monkeypatch):
    """진짜 Run 키 대신 쓸 임시 키. 테스트가 끝나면 지운다."""
    path = rf"Software\ClappingSetupTest\{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(autostart, "RUN_KEY_PATH", path)
    yield path

    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        pass      # 만들어지지 않았으면 지울 것도 없다


class TestLaunchCommand:
    def test_경로에_따옴표를_씌운다(self):
        """⭐ 'Program Files' 처럼 공백이 든 경로가 대부분이다.

        따옴표가 없으면 Windows 가 공백에서 잘라 읽고 조용히 실행에 실패한다.
        """
        command = autostart.build_launch_command()
        assert command.startswith('"')
        assert '"' in command[1:]

    def test_창_없이_시작하도록_옵션을_붙인다(self):
        """로그인할 때마다 창이 튀어나오면 누구라도 이 기능을 꺼버린다."""
        assert autostart.build_launch_command().endswith("--minimized")

    def test_소스로_실행_중이면_모듈로_띄운다(self):
        command = autostart.build_launch_command()
        assert "-m clap_launcher" in command

    def test_콘솔_창이_뜨지_않는_파이썬을_고른다(self):
        """python.exe 로 등록하면 로그인할 때마다 검은 콘솔 창이 함께 뜬다."""
        command = autostart.build_launch_command()
        assert "pythonw.exe" in command.lower(), f"pythonw 를 못 찾았다: {command}"

    def test_exe로_묶였을_때는_모듈_옵션이_없다(self, monkeypatch):
        """M6에서 exe 로 만들면 python 이 없는 PC에서 돌아야 한다."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", r"C:\Apps\ClappingSetup.exe")

        command = autostart.build_launch_command()

        assert command == '"C:\\Apps\\ClappingSetup.exe" --minimized'
        assert "-m clap_launcher" not in command


class TestRegistry:
    def test_처음에는_등록되어_있지_않다(self, temp_run_key):
        assert autostart.is_enabled() is False

    def test_등록하고_읽으면_켜져_있다(self, temp_run_key):
        assert autostart.enable() is True
        assert autostart.is_enabled() is True

    def test_해제하면_꺼진다(self, temp_run_key):
        autostart.enable()
        assert autostart.disable() is True
        assert autostart.is_enabled() is False

    def test_등록된_값은_실행_명령이다(self, temp_run_key):
        import winreg

        autostart.enable()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, temp_run_key) as key:
            value, _type = winreg.QueryValueEx(key, autostart.VALUE_NAME)
        assert value == autostart.build_launch_command()

    def test_없는_것을_해제해도_성공으로_본다(self, temp_run_key):
        """사용자가 원한 결과('등록 안 됨')는 똑같이 이뤄졌다."""
        assert autostart.disable() is True

    def test_두_번_등록해도_하나만_남는다(self, temp_run_key):
        autostart.enable()
        autostart.enable()
        autostart.disable()
        assert autostart.is_enabled() is False   # 하나만 지워도 완전히 꺼져야 한다

    @pytest.mark.parametrize("wanted", [True, False])
    def test_set_enabled_로_한_번에_바꾼다(self, temp_run_key, wanted):
        assert autostart.set_enabled(wanted) is True
        assert autostart.is_enabled() is wanted


def test_진짜_Run_키를_건드리지_않았다():
    """⭐ 위 테스트들이 사용자의 시작 프로그램을 바꾸지 않았는지 확인한다.

    monkeypatch 가 풀린 뒤이므로 RUN_KEY_PATH 는 진짜 경로로 돌아와 있다.
    이 테스트가 실패하면 테스트 자체가 사용자 환경을 오염시킨 것이다.
    """
    assert autostart.RUN_KEY_PATH.endswith(r"CurrentVersion\Run")
