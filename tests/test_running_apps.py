"""중복 실행 방지 테스트.

'이미 켜져 있으면 건너뛴다'가 잘못 동작하면 두 가지 나쁜 일이 생긴다.
  · 너무 많이 건너뜀 → 박수를 쳤는데 아무것도 안 켜진다 (고장으로 보인다)
  · 너무 적게 건너뜀 → 창이 두 개씩 뜬다 (원래 문제로 돌아간다)

실제 프로세스 목록을 읽는 부분은 기기마다 다르므로, 비교 로직만 값으로 검증한다.
"""

import sys

import pytest

from clap_launcher.config import AppEntry
from clap_launcher.launcher.app_launcher import AppLauncher
from clap_launcher.launcher.running_apps import (
    executable_name,
    is_already_running,
    list_running_processes,
)


class TestExecutableName:
    @pytest.mark.parametrize("path,expected", [
        ("C:/Program Files/Microsoft VS Code/Code.exe", "code.exe"),
        (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "chrome.exe"),
        ("Code.exe", "code.exe"),
        ("  C:/a/b/Slack.exe  ", "slack.exe"),
        ("", ""),
    ])
    def test_이름만_소문자로_뽑는다(self, path, expected):
        """대소문자·역슬래시가 뒤섞여 들어와도 같은 값이 나와야 한다."""
        assert executable_name(path) == expected


class TestIsAlreadyRunning:
    def test_돌고_있으면_True(self):
        assert is_already_running("C:/x/Code.exe", {"code.exe", "chrome.exe"})

    def test_대소문자가_달라도_찾는다(self):
        """설정에는 Code.exe, 프로세스 목록에는 code.exe 로 들어온다."""
        assert is_already_running("C:/x/CODE.EXE", {"code.exe"})

    def test_안_돌고_있으면_False(self):
        assert not is_already_running("C:/x/Code.exe", {"chrome.exe"})

    def test_목록이_비면_False(self):
        """프로세스 조회에 실패하면 빈 집합이 온다. 그때는 평소처럼 전부 실행해야 한다."""
        assert not is_already_running("C:/x/Code.exe", set())

    def test_경로가_비면_False(self):
        assert not is_already_running("", {"code.exe"})


def test_실제_프로세스_목록을_읽을_수_있다():
    """⭐ 지금 이 테스트를 돌리는 파이썬은 반드시 목록에 있어야 한다.

    ctypes 구조체가 조금만 어긋나도 조용히 빈 집합이 나오는데,
    그러면 중복 방지가 '항상 꺼진 상태'로 동작하게 된다.
    """
    running = list_running_processes()
    if sys.platform != "win32":
        assert running == set()
        return

    assert running, "프로세스 목록이 비었다 — ctypes 호출이 실패했을 가능성이 높다"
    assert any(name.startswith("python") for name in running), \
        f"지금 돌고 있는 python 이 목록에 없다: {sorted(running)[:10]}"


class TestLauncherSkips:
    """실행기가 중복 검사를 실제로 반영하는지."""

    def _launcher(self, running: set[str], calls: list):
        def fake(entry):
            calls.append(entry.name)
        return AppLauncher(launchers={"exe": fake, "url": fake},
                           sleep=lambda _s: None, running_lookup=lambda: running)

    def test_이미_켜져_있으면_실행하지_않는다(self):
        calls = []
        launcher = self._launcher({"code.exe"}, calls)

        result = launcher.launch_all([AppEntry(name="VS Code", path="C:/x/Code.exe")])

        assert calls == []
        assert result.already_running == ["VS Code"]
        assert result.succeeded == []
        assert result.ok            # 실패가 아니다. 정상적으로 건너뛴 것이다

    def test_안_켜져_있으면_실행한다(self):
        calls = []
        result = self._launcher({"chrome.exe"}, calls).launch_all(
            [AppEntry(name="VS Code", path="C:/x/Code.exe")])

        assert calls == ["VS Code"]
        assert result.already_running == []

    def test_skip_if_running_false_면_또_켠다(self):
        """브라우저처럼 창을 하나 더 띄우고 싶은 경우를 위한 도피구."""
        calls = []
        result = self._launcher({"chrome.exe"}, calls).launch_all(
            [AppEntry(name="Chrome", path="C:/x/chrome.exe", skip_if_running=False)])

        assert calls == ["Chrome"]
        assert result.already_running == []

    def test_웹주소는_중복_검사를_하지_않는다(self):
        """탭을 하나 더 여는 게 자연스럽다. '켜져 있다'는 개념도 애매하다."""
        calls = []
        result = self._launcher({"chrome.exe"}, calls).launch_all(
            [AppEntry(name="깃허브", path="https://github.com", type="url")])

        assert calls == ["깃허브"]
        assert result.already_running == []

    def test_건너뛴_항목의_delay는_기다리지_않는다(self):
        """아무것도 안 켰으니 시스템이 바쁠 이유가 없다."""
        slept = []
        launcher = AppLauncher(launchers={"exe": lambda e: None}, sleep=slept.append,
                               running_lookup=lambda: {"code.exe"})

        launcher.launch_all([AppEntry(name="A", path="C:/x/Code.exe", delay=3.0),
                             AppEntry(name="B", path="C:/x/Other.exe")])

        assert slept == []

    def test_전부_웹주소면_프로세스_목록을_읽지_않는다(self):
        """목록을 읽는 데 시간이 든다. 필요 없을 때는 건드리지 않는다."""
        looked = []

        def lookup():
            looked.append(True)
            return set()

        AppLauncher(launchers={"url": lambda e: None}, sleep=lambda _s: None,
                    running_lookup=lookup).launch_all(
            [AppEntry(name="A", path="https://a.com", type="url")])

        assert looked == []

    def test_요약에_이미_켜져_있음이_들어간다(self):
        """'아무 일도 안 일어났다'로 보이면 사용자는 고장으로 오해한다."""
        result = self._launcher({"code.exe"}, []).launch_all(
            [AppEntry(name="VS Code", path="C:/x/Code.exe")])
        assert "이미 켜져 있음 1개" in result.summary()
