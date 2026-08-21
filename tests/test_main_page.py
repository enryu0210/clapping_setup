"""메인 화면의 '박수 감지 → 프리셋 찾기 → 프로그램 실행' 연결 테스트.

진짜 박수를 쳐서 확인하려면 마이크도 있어야 하고 사람도 있어야 한다.
그래서 마이크와 실행기를 **가짜로 바꿔 끼워** 연결이 제대로 되어 있는지만 확인한다.

여기서 확인하는 것:
  ⭐ 박수를 감지하면 마이크를 먼저 놓고 나서 프로그램을 실행한다 (순서가 중요하다)
  ⭐ **친 횟수에 맞는 프리셋**이 실행된다 (3번을 쳤는데 2번 묶음이 켜지면 안 된다)
  ⭐ 설정 파일이 잘못돼 있으면 **박수를 치기 전에** 화면에 알려준다
  ⭐ 실행 전 취소 배너가 실제로 실행을 막는다
"""

import pytest

from clap_launcher.config import CONFIG_ENV_VAR, AppEntry
from clap_launcher.launcher.app_launcher import LaunchResult
from clap_launcher.listening import StopReason
from clap_launcher.settings import Settings
from clap_launcher.ui import theme
from clap_launcher.ui.audio_monitor import MonitorSnapshot

# 2번과 3번에 서로 다른 묶음을 둔 설정. '횟수에 맞는 묶음을 고르는가'를 보려면
# 최소한 두 묶음이 서로 달라야 한다.
GOOD_CONFIG = """
presets:
  - claps: 2
    name: 일
    apps:
      - name: 메모장
        type: exe
        path: "C:/Windows/System32/notepad.exe"
  - claps: 3
    name: 취미
    apps:
      - name: 계산기
        type: exe
        path: "C:/Windows/System32/calc.exe"
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


class InstantThread:
    """start() 하면 그 자리에서 바로 실행하는 가짜 스레드.

    ⚠️ 이게 없으면 테스트가 **가끔** 통과한다. 진짜 실행은 별도 스레드에서 도는데,
       테스트는 그 스레드가 끝났는지 알 방법이 없어 "아직 실행 중…"인 화면을 보고
       실패한다. 실제로 그렇게 흔들리는 테스트를 겪었다.
    """

    def __init__(self, target=None, args=(), **_kwargs) -> None:
        self._target = target
        self._args = args

    def start(self) -> None:
        self._target(*self._args)


@pytest.fixture
def make_page(root, tmp_path, monkeypatch):
    """설정 파일을 임시로 깔아두고 메인 화면을 만든다.

    만든 화면은 테스트가 끝나면 지운다. 창 하나를 계속 쓰므로 치우지 않으면
    이전 테스트의 화면이 그대로 쌓인다.

    ⚠️ 기본값으로 취소 배너를 꺼둔다(launch_confirm_sec=0). 대부분의 테스트는
       '무엇이 실행되는가'를 보려는 것인데, 배너가 켜져 있으면 3초를 기다리거나
       타이머를 흉내 내야 해서 정작 보려던 것이 가려진다.
       배너 자체는 아래 TestConfirmBanner 에서 따로 확인한다.
    """
    made = []

    def _make(config_text: str | None = GOOD_CONFIG, confirm_sec: float = 0.0):
        """config_text=None 이면 설정 파일 자체를 만들지 않는다 (갓 설치한 상태)."""
        path = tmp_path / "apps.yaml"
        if config_text is not None:
            path.write_text(config_text, encoding="utf-8")
            monkeypatch.setenv(CONFIG_ENV_VAR, str(path))

        from clap_launcher.ui import main_page as main_page_module
        from clap_launcher.ui.main_page import MainPage

        monkeypatch.setattr(main_page_module.threading, "Thread", InstantThread)

        monitor = FakeMonitor()
        settings = Settings(device=None, setup_done=True, launch_confirm_sec=confirm_sec)
        page = MainPage(root, monitor, settings,
                        on_change_device=lambda: None, on_calibrate=lambda: None)
        made.append(page)
        return page, monitor

    yield _make
    for page in made:
        page._clear_pending()      # 남은 after() 예약이 다음 테스트로 새지 않게
        page.destroy()


class TestStartup:
    def test_켜자마자_어느_횟수에_무엇이_실행되는지_보여준다(self, make_page):
        """프리셋이 넷이면 '몇 번에 뭐가 켜지는지'를 기억하기 어렵다. 화면이 대신 기억한다."""
        page, _monitor = make_page()
        text = page.launch_label.cget("text")
        assert "2번" in text and "메모장" in text
        assert "3번" in text and "계산기" in text

    def test_설정이_잘못됐으면_박수를_치기_전에_알려준다(self, make_page):
        """⭐ 박수를 친 순간에 '설정이 없다'고 하면 가장 김이 새는 순간에 김이 샌다."""
        page, _monitor = make_page("presets:\n  - claps: 2\n    apps:\n      - name: 이름만있음\n")
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
        page._handle_trigger = lambda claps: order.append(f"{claps}번 처리")

        monitor.value = MonitorSnapshot(trigger_count=1, last_trigger_claps=2, event_count=0)
        page.update_from_monitor()

        assert order == ["마이크 놓음", "2번 처리"]
        assert not page.session.armed
        assert page.session.stop_reason is StopReason.TRIGGERED

    def test_친_횟수가_그대로_넘어간다(self, make_page):
        """⭐ 여기가 어긋나면 4번을 쳤는데 2번 묶음이 켜진다."""
        page, monitor = make_page()
        seen = []
        page._handle_trigger = seen.append

        monitor.value = MonitorSnapshot(trigger_count=1, last_trigger_claps=4)
        page.update_from_monitor()

        assert seen == [4]

    def test_박수가_없으면_실행하지_않는다(self, make_page):
        page, monitor = make_page()
        called = []
        page._handle_trigger = called.append

        monitor.value = MonitorSnapshot(trigger_count=0)
        page.update_from_monitor()

        assert called == []
        assert page.session.armed


class TestPresetChoice:
    """⭐ 이 프로젝트에서 프리셋이 하는 일의 전부: 친 횟수로 묶음을 고른다."""

    def test_2번이면_2번_묶음이_실행된다(self, make_page, root):
        page, _monitor = make_page()
        launcher = FakeLauncher()
        page._launcher = launcher

        page._handle_trigger(2)
        root.update()

        assert [app.name for app in launcher.received] == ["메모장"]

    def test_3번이면_3번_묶음이_실행된다(self, make_page, root):
        page, _monitor = make_page()
        launcher = FakeLauncher()
        page._launcher = launcher

        page._handle_trigger(3)
        root.update()

        assert [app.name for app in launcher.received] == ["계산기"]

    def test_등록되지_않은_횟수는_아무것도_실행하지_않고_이유를_말한다(self, make_page):
        """⭐ 조용히 끝나면 사용자는 감지가 안 된 줄 알고 계속 더 크게 박수를 친다."""
        page, _monitor = make_page()
        launcher = FakeLauncher()
        page._launcher = launcher

        page._handle_trigger(5)

        assert launcher.received == []
        text = page.launch_label.cget("text")
        assert "5번" in text and "없습니다" in text

    def test_전부_꺼둔_묶음은_등록되지_않은_것으로_본다(self, make_page):
        """사용자 눈에는 '박수를 쳤는데 아무 일도 없다'로 똑같다. 이유를 말해줘야 한다."""
        page, _monitor = make_page("""
presets:
  - claps: 2
    apps:
      - name: 꺼둔것
        type: url
        path: "https://a.com"
        enabled: false
""")
        page._handle_trigger(2)
        assert "없습니다" in page.launch_label.cget("text")


class TestConfirmBanner:
    """실행 직전 취소 배너. 횟수를 잘못 세었을 때 되돌릴 유일한 수단이다."""

    def test_바로_실행하지_않고_기다린다(self, make_page):
        page, _monitor = make_page(confirm_sec=3.0)
        launcher = FakeLauncher()
        page._launcher = launcher

        page._handle_trigger(2)

        assert launcher.received == []                     # 아직 실행 전
        assert page._pending_preset is not None
        text = page.launch_label.cget("text")
        assert "2번" in text and "실행 취소" in text        # 되돌리는 방법을 알려준다

    def test_취소하면_실행되지_않고_다시_듣는다(self, make_page):
        page, monitor = make_page(confirm_sec=3.0)
        launcher = FakeLauncher()
        page._launcher = launcher
        before = monitor.start_count

        page._handle_trigger(2)
        page._cancel_pending_launch()

        assert launcher.received == []
        assert page._pending_preset is None
        assert monitor.start_count == before + 1     # 다시 듣기 시작한다

    def test_시간이_다_되면_실행된다(self, make_page, root):
        page, _monitor = make_page(confirm_sec=3.0)
        launcher = FakeLauncher()
        page._launcher = launcher

        page._handle_trigger(2)
        # 1초씩 흐르는 것을 기다리지 않고, 남은 시간을 0으로 만든 뒤 다음 눈금을 직접 부른다
        page._pending_left = 0
        page._pending_tick()
        root.update()

        assert [app.name for app in launcher.received] == ["메모장"]
        assert page._pending_preset is None

    def test_다른_화면으로_가면_예약이_끊긴다(self, make_page):
        """⭐ 안 끊으면 설정 화면에 있는 동안 프로그램들이 뒤에서 켜진다."""
        page, _monitor = make_page(confirm_sec=3.0)
        launcher = FakeLauncher()
        page._launcher = launcher

        page._handle_trigger(2)
        page._leave_to(lambda: None)

        assert page._pending_preset is None
        assert launcher.received == []


class TestLaunch:
    def test_실패하면_이유가_화면에_남는다(self, make_page, root):
        page, _monitor = make_page()
        page._launcher = FakeLauncher(
            LaunchResult(failed=[("메모장", "경로를 찾을 수 없습니다")]))

        page._handle_trigger(2)
        root.update()

        assert "경로를 찾을 수 없습니다" in page.launch_label.cget("text")

    def test_이미_실행_중이면_또_실행하지_않는다(self, make_page):
        """실행에 몇 초가 걸리는 사이에 또 발동하면 프로그램이 두 번 켜진다."""
        page, _monitor = make_page()
        launcher = FakeLauncher()
        page._launcher = launcher
        page._launching = True

        page._handle_trigger(2)

        assert launcher.received == []

    def test_설정_파일이_사라져도_죽지_않는다(self, make_page, tmp_path):
        """실행 중에 사용자가 파일을 지우거나 고치다 깨뜨릴 수 있다."""
        page, _monitor = make_page()
        (tmp_path / "apps.yaml").unlink()

        page._handle_trigger(2)      # 예외가 새어 나오면 창이 통째로 죽는다

        # 파일이 없어진 것은 '등록된 게 없는' 상태와 같다. 겁주지 않고 할 일을 알려준다.
        assert "프로그램 설정" in page.launch_label.cget("text")

    def test_설정이_깨진_경우에는_빨간_경고를_띄운다(self, make_page):
        """⭐ '아직 등록 안 함'과 '설정이 깨짐'은 다르다. 후자만 경고여야 한다."""
        page, _monitor = make_page("presets:\n  - claps: 2\n    apps:\n      - name: 경로없음\n")
        page._handle_trigger(2)
        assert str(page.launch_label.cget("foreground")) == theme.ERROR
