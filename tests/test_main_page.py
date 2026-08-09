"""메인 화면의 '박수 감지 → 프로그램 실행' 연결 테스트.

진짜 박수를 쳐서 확인하려면 마이크도 있어야 하고 사람도 있어야 한다.
그래서 마이크와 실행기를 **가짜로 바꿔 끼워** 연결이 제대로 되어 있는지만 확인한다.

여기서 확인하는 것:
  ⭐ 박수를 감지하면 마이크를 먼저 놓고 나서 프로그램을 실행한다 (순서가 중요하다)
  ⭐ 설정 파일이 잘못돼 있으면 **박수를 치기 전에** 화면에 알려준다
"""

import pytest

from clap_launcher.config import CONFIG_ENV_VAR, AppEntry
from clap_launcher.launcher.app_launcher import LaunchResult
from clap_launcher.listening import StopReason
from clap_launcher.settings import Settings
from clap_launcher.ui import theme
from clap_launcher.ui.audio_monitor import MonitorSnapshot

GOOD_CONFIG = """
apps:
  - name: 메모장
    type: exe
    path: "C:/Windows/System32/notepad.exe"
"""


# root(숨긴 Tk 창) 는 conftest.py 에 있다. 창은 테스트 전체에서 하나만 쓴다.
# 테스트마다 새로 만들면 그림자 이미지(PIL)가 이전 창에 묶인 채로 남아
# 'image "pyimage1" doesn't exist' 로 죽는다. 실제로 여기서 겪은 문제다.


class FakeMonitor:
    """마이크를 열지 않는 가짜 모니터. 언제 열고 닫았는지만 기록한다."""

    def __init__(self) -> None:
        self.value = MonitorSnapshot()
        self.start_count = 0
        self.stop_count = 0

    def start(self, device, detection=None) -> None:
        self.start_count += 1

    def stop(self) -> None:
        self.stop_count += 1

    def snapshot(self) -> MonitorSnapshot:
        return self.value


class FakeLauncher:
    """실행한 척만 한다. 무엇을 넘겨받았는지 기록한다."""

    def __init__(self, result: LaunchResult | None = None) -> None:
        self.received: list[AppEntry] = []
        self.result = result or LaunchResult(succeeded=["메모장"])

    def launch_all(self, apps) -> LaunchResult:
        self.received = list(apps)
        return self.result


@pytest.fixture
def make_page(root, tmp_path, monkeypatch):
    """설정 파일을 임시로 깔아두고 메인 화면을 만든다.

    만든 화면은 테스트가 끝나면 지운다. 창 하나를 계속 쓰므로 치우지 않으면
    이전 테스트의 화면이 그대로 쌓인다.
    """
    made = []

    def _make(config_text: str | None = GOOD_CONFIG):
        """config_text=None 이면 설정 파일 자체를 만들지 않는다 (갓 설치한 상태)."""
        path = tmp_path / "apps.yaml"
        if config_text is not None:
            path.write_text(config_text, encoding="utf-8")
            monkeypatch.setenv(CONFIG_ENV_VAR, str(path))

        from clap_launcher.ui.main_page import MainPage

        monitor = FakeMonitor()
        page = MainPage(root, monitor, Settings(device=None, setup_done=True),
                        on_change_device=lambda: None, on_calibrate=lambda: None)
        made.append(page)
        return page, monitor

    yield _make
    for page in made:
        page.destroy()


class TestStartup:
    def test_켜자마자_무엇이_실행되는지_보여준다(self, make_page):
        page, _monitor = make_page()
        assert "메모장" in page.launch_label.cget("text")

    def test_설정이_잘못됐으면_박수를_치기_전에_알려준다(self, make_page):
        """⭐ 박수를 친 순간에 '설정이 없다'고 하면 가장 김이 새는 순간에 김이 샌다."""
        page, _monitor = make_page("apps:\n  - name: 이름만있음\n")
        assert "path" in page.launch_label.cget("text")

    def test_설정_파일이_아직_없는_것은_오류가_아니다(self, make_page, tmp_path, monkeypatch):
        """⭐ 갓 설치한 사람의 정상적인 상태다.

        이걸 오류로 다루면 첫 실행 화면에 빨간 경고가 **계속 떠 있는다.**
        실제로 그렇게 배포됐고, 사용자가 스크린샷을 찍어 보내왔다.
        """
        monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "아직없는파일.yaml"))
        page, _monitor = make_page(config_text=None)

        text = page.launch_label.cget("text")
        assert "찾지 못했습니다" not in text        # 파일 경로 나열도 하지 않는다
        assert "프로그램 설정" in text              # 다음에 할 일을 알려준다
        # ⚠️ Tk 는 파이썬 str 이 아닌 Tcl 문자열을 준다. str() 로 감싸지 않으면
        #    비교가 항상 참이 되어 **통과하는 척하는 테스트**가 된다.
        assert str(page.launch_label.cget("foreground")) != theme.ERROR

    def test_켜자마자_듣기를_시작한다(self, make_page):
        _page, monitor = make_page()
        assert monitor.start_count == 1


class TestTrigger:
    def test_박수를_감지하면_마이크를_놓고_실행한다(self, make_page):
        """⭐ 순서가 중요하다. 실행이 끝날 때까지 마이크를 잡고 있으면 또 발동할 여지가 생긴다."""
        page, monitor = make_page()
        order = []
        monitor.stop = lambda: order.append("마이크 놓음")
        page.launch_apps = lambda: order.append("프로그램 실행")

        monitor.value = MonitorSnapshot(trigger_count=1, event_count=0)
        page.update_from_monitor()

        assert order == ["마이크 놓음", "프로그램 실행"]
        assert not page.session.armed
        assert page.session.stop_reason is StopReason.TRIGGERED

    def test_박수가_없으면_실행하지_않는다(self, make_page):
        page, monitor = make_page()
        called = []
        page.launch_apps = lambda: called.append(1)

        monitor.value = MonitorSnapshot(trigger_count=0)
        page.update_from_monitor()

        assert called == []
        assert page.session.armed


class TestLaunch:
    def test_설정에_적힌_항목을_실행기에_넘긴다(self, make_page, root):
        page, _monitor = make_page()
        launcher = FakeLauncher()
        page._launcher = launcher

        page._run_launch(page._load_apps()[0])   # 스레드 본체를 직접 부른다(순서 고정)
        root.update()                            # after(0) 로 미뤄둔 화면 갱신을 처리

        assert [app.name for app in launcher.received] == ["메모장"]
        assert "성공 1개" in page.launch_label.cget("text")

    def test_실패하면_이유가_화면에_남는다(self, make_page, root):
        page, _monitor = make_page()
        page._launcher = FakeLauncher(
            LaunchResult(failed=[("메모장", "경로를 찾을 수 없습니다")]))

        page._run_launch(page._load_apps()[0])
        root.update()

        assert "경로를 찾을 수 없습니다" in page.launch_label.cget("text")

    def test_실행할_것이_없으면_그렇다고_알려준다(self, make_page):
        page, _monitor = make_page("apps: []\n")
        page.launch_apps()
        assert "실행할 프로그램이 없습니다" in page.launch_label.cget("text")

    def test_이미_실행_중이면_또_실행하지_않는다(self, make_page):
        """실행에 몇 초가 걸리는 사이에 또 발동하면 프로그램이 두 번 켜진다."""
        page, _monitor = make_page()
        launcher = FakeLauncher()
        page._launcher = launcher
        page._launching = True

        page.launch_apps()

        assert launcher.received == []

    def test_설정_파일이_사라져도_죽지_않는다(self, make_page, tmp_path):
        """실행 중에 사용자가 파일을 지우거나 고치다 깨뜨릴 수 있다."""
        page, _monitor = make_page()
        (tmp_path / "apps.yaml").unlink()

        page.launch_apps()      # 예외가 새어 나오면 창이 통째로 죽는다

        # 파일이 없어진 것은 '등록된 게 없는' 상태와 같다. 겁주지 않고 할 일을 알려준다.
        assert "프로그램 설정" in page.launch_label.cget("text")

    def test_설정이_깨진_경우에는_빨간_경고를_띄운다(self, make_page):
        """⭐ '아직 등록 안 함'과 '설정이 깨짐'은 다르다. 후자만 경고여야 한다."""
        page, _monitor = make_page("apps:\n  - name: 경로없음\n")
        page.launch_apps()
        assert str(page.launch_label.cget("foreground")) == theme.ERROR
