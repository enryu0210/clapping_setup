"""창 전체를 관리하는 곳 — 화면 전환, 주기적 갱신, 종료 처리.

화면(페이지)을 갈아끼우는 방식으로 만든 이유:
창을 여러 개 띄우면 작업표시줄이 지저분해지고, 창 사이 상태를 주고받기도 번거롭다.
창은 하나만 두고 내용물만 바꾸면 훨씬 단순하다.

  첫 실행         → DevicePage (마이크 선택)
  선택을 마친 뒤  → MainPage   (상태 표시)
"""

import tkinter as tk
from tkinter import ttk

from ..console import force_utf8_console
from ..session_lock import LockWatcher, is_session_locked
from ..settings import Settings, load_settings
from . import theme
from .audio_monitor import AudioMonitor
from .calibrate_page import CalibratePage
from .device_page import DevicePage
from .main_page import MainPage

WINDOW_TITLE = "Clapping Setup"
WINDOW_SIZE = "620x790"   # 메인 화면에 '무엇이 실행되는지' 줄이 생겨 조금 키웠다
UI_REFRESH_MS = 50        # 화면 갱신 주기. 20fps면 막대가 충분히 부드럽다.
LOCK_POLL_MS = 1500       # 화면 잠금 상태를 확인하는 주기.
# 1.5초면 충분한 이유: 잠금이 풀린 걸 1초 늦게 알아도 사용자는 아직 자리에 앉는 중이다.
# 더 자주 물어봐야 할 이유가 없고, Windows API 호출도 공짜는 아니다.


def _enable_dpi_awareness() -> None:
    """고해상도 모니터에서 글씨가 뿌옇게 보이는 것을 막는다.

    Windows 전용 기능이라 실패해도 그냥 넘어간다(다른 OS이거나 옛날 Windows).
    """
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


class ClapLauncherApp(tk.Tk):
    """프로그램의 창 하나."""

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings if settings is not None else load_settings()
        self.monitor = AudioMonitor()
        self.current_page: ttk.Frame | None = None
        self._closed = False   # 정리를 두 번 하지 않기 위한 표시
        self._lock_watcher = LockWatcher()

        self.title(WINDOW_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(600, 750)
        self.configure(bg=theme.BG)
        self._setup_styles()

        # 창의 X 버튼을 눌렀을 때 오디오 스레드를 정리하고 나가도록 가로챈다.
        # 이걸 안 하면 창은 사라졌는데 프로세스가 남는 일이 생긴다.
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)

        # 마이크를 아직 고른 적이 없으면 선택 화면부터 보여준다
        if self.settings.setup_done:
            self.show_main_page()
        else:
            self.show_device_page()

        self._bring_to_front()
        self.after(UI_REFRESH_MS, self._tick)
        self.after(LOCK_POLL_MS, self._check_session_lock)

    def _bring_to_front(self) -> None:
        """창을 확실히 맨 앞에 띄운다.

        터미널에서 실행하면 Tk 창이 터미널 **뒤에** 열리는 경우가 있다.
        사용자 입장에서는 아무 일도 안 일어난 것처럼 보여서 Ctrl+C 를 누르게 된다.
        잠깐만 '항상 위'로 올렸다가 바로 풀어준다. 계속 위로 두면 다른 작업에 방해가 된다.
        """
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.after(200, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except tk.TclError:
            pass   # 창 띄우기에 실패해도 프로그램이 죽을 이유는 없다

    def _setup_styles(self) -> None:
        """ttk 위젯의 색과 글꼴을 한 번에 정한다.

        버튼·토글·패널은 뉴모피즘 부품(neumorphic.py)이 대신하므로,
        여기서는 글자와 스크롤바처럼 남은 것들만 배경색에 맞춰 준다.
        """
        style = ttk.Style(self)
        # 'clam' 테마를 쓰는 이유: Windows 기본 테마는 배경색 지정이 잘 먹지 않는다.
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=theme.BG)
        style.configure("TLabel", background=theme.BG, foreground=theme.FG,
                        font=theme.FONT_BODY)
        style.configure("Title.TLabel", font=theme.FONT_TITLE, foreground=theme.FG)
        style.configure("Heading.TLabel", font=theme.FONT_HEADING, foreground=theme.FG)
        style.configure("Muted.TLabel", foreground=theme.FG_MUTED, font=theme.FONT_BODY)
        style.configure("Small.TLabel", foreground=theme.FG_MUTED, font=theme.FONT_SMALL)
        style.configure("Mono.TLabel", foreground=theme.FG, font=theme.FONT_MONO)

        # 패널 안쪽(움푹 들어간 바닥) 위에 놓이는 글자는 배경색이 다르다
        style.configure("Sunken.TLabel", background=theme.BG_SUNKEN,
                        foreground=theme.FG_MUTED, font=theme.FONT_SMALL)

        style.configure("TScrollbar", background=theme.BG_SUNKEN, troughcolor=theme.BG_SUNKEN,
                        borderwidth=0, arrowcolor=theme.FG_MUTED)
        style.map("TScrollbar", background=[("active", theme.DARK)])

    # ── 화면 전환 ──────────────────────────────────────────
    def _swap_page(self, page: ttk.Frame) -> None:
        if self.current_page is not None:
            self.current_page.destroy()
        self.current_page = page
        page.pack(fill="both", expand=True)

    def show_device_page(self) -> None:
        self._swap_page(DevicePage(self.container, self.monitor, self.settings,
                                   on_done=self.show_main_page))

    def show_main_page(self) -> None:
        # 마이크를 언제 열고 닫을지는 메인 화면이 스스로 관리한다(듣는 중 / 대기 중).
        # 여기서 monitor.start 를 부르면 그 상태 관리와 어긋난다.
        self._swap_page(MainPage(self.container, self.monitor, self.settings,
                                 on_change_device=self.show_device_page,
                                 on_calibrate=self.show_calibrate_page))

    def show_calibrate_page(self) -> None:
        self._swap_page(CalibratePage(self.container, self.monitor, self.settings,
                                      on_done=self.show_main_page))

    # ── 주기적 갱신 ────────────────────────────────────────
    def _tick(self) -> None:
        """50ms마다 현재 화면에게 '최신 값으로 갱신하라'고 알린다.

        오디오 스레드가 화면을 직접 건드리면 안 되므로, 화면 쪽에서 읽어가는 방식을 쓴다.
        (Tkinter 위젯은 메인 스레드에서만 만질 수 있다)
        """
        page = self.current_page
        if page is not None and hasattr(page, "update_from_monitor"):
            try:
                page.update_from_monitor()
            except tk.TclError:
                return   # 창이 닫히는 중이면 조용히 멈춘다
        self.after(UI_REFRESH_MS, self._tick)

    def _check_session_lock(self) -> None:
        """화면 잠금이 방금 풀렸으면 현재 화면에 알려준다.

        Windows 세션 알림을 제대로 받으려면 창 핸들과 메시지 루프가 필요해 Tkinter와
        엮기 까다롭다. 잠금 해제를 1~2초 늦게 알아도 아무 문제가 없으므로
        주기적으로 물어보는 방식을 쓴다.
        """
        if self._closed:
            return

        try:
            just_unlocked = self._lock_watcher.update(is_session_locked())
        except Exception:
            just_unlocked = False   # 잠금 감지가 실패해도 프로그램 본체는 계속 돌아야 한다

        page = self.current_page
        if just_unlocked and page is not None and hasattr(page, "on_session_unlocked"):
            try:
                page.on_session_unlocked()
            except tk.TclError:
                return   # 창이 닫히는 중

        self.after(LOCK_POLL_MS, self._check_session_lock)

    def on_close(self) -> None:
        """창을 닫을 때 오디오 스레드를 확실히 멈추고 나간다.

        여러 번 불려도 안전해야 한다: 사용자가 X를 누른 뒤에도 마무리 정리(finally)에서
        한 번 더 부르기 때문이다. 이미 닫힌 창에 destroy()를 부르면 오류가 난다.
        """
        if self._closed:
            return
        self._closed = True
        self.monitor.stop()
        try:
            self.destroy()
        except tk.TclError:
            pass   # 이미 창이 사라진 상태 — 정상적인 종료 경로다


def run_gui() -> int:
    """GUI를 띄운다. 종료 코드를 반환한다."""
    # GUI라도 오류 메시지는 콘솔로 나가므로 인코딩을 먼저 맞춰둔다
    force_utf8_console()
    _enable_dpi_awareness()
    app = ClapLauncherApp()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        # 터미널에서 Ctrl+C 로 끄는 것은 '오류'가 아니라 정상적인 종료 방법이다.
        # 그냥 두면 파이썬 traceback이 그대로 쏟아져서 사용자는 프로그램이 고장 난 줄 안다.
        print("\n종료합니다.")
    finally:
        # 어떻게 끝났든 마이크는 반드시 놓아준다.
        # 이걸 빠뜨리면 창은 사라졌는데 마이크를 붙잡은 프로세스가 남는다.
        app.on_close()
    return 0
