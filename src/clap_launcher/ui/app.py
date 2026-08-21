"""창 전체를 관리하는 곳 — 화면 전환, 주기적 갱신, 종료 처리.

화면(페이지)을 갈아끼우는 방식으로 만든 이유:
창을 여러 개 띄우면 작업표시줄이 지저분해지고, 창 사이 상태를 주고받기도 번거롭다.
창은 하나만 두고 내용물만 바꾸면 훨씬 단순하다.

  첫 실행         → DevicePage (마이크 선택)
  선택을 마친 뒤  → MainPage   (상태 표시)
"""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ..console import force_utf8_console
from ..session_lock import LockWatcher, is_session_locked
from ..settings import Settings, load_settings, save_settings
from . import icons, theme
from .apps_page import AppsPage
from .audio_monitor import AudioMonitor
from .calibrate_page import CalibratePage
from .device_page import DevicePage
from .main_page import MainPage
from .tray import TrayIcon

WINDOW_TITLE = "ClapDesk"
# 창 크기는 96 DPI 기준. 고해상도 화면에서는 theme.px() 로 함께 커진다.
# ⚠️ 가장 크게 필요한 화면(프로그램 설정)에 맞춰야 한다. 그 화면이 잘리면 [저장] 버튼이
#    창 밖으로 밀려 저장을 할 수 없게 된다. 프리셋 탭 네 개가 가로로 늘어서고 세로도
#    두 줄 늘어나서 620x765 → 640x800 으로 키웠다.
#    (더 키우지 않는 이유: 배율 125% 화면에서 1000px 을 넘으면 작업표시줄에 가린다)
WINDOW_WIDTH, WINDOW_HEIGHT = 640, 800
UI_REFRESH_MS = 50        # 화면 갱신 주기. 20fps면 막대가 충분히 부드럽다.
LOCK_POLL_MS = 1500       # 화면 잠금 상태를 확인하는 주기.
# 1.5초면 충분한 이유: 잠금이 풀린 걸 1초 늦게 알아도 사용자는 아직 자리에 앉는 중이다.
# 더 자주 물어봐야 할 이유가 없고, Windows API 호출도 공짜는 아니다.


def app_icon_path() -> Path | None:
    """앱 아이콘 파일(assets/icon.ico)의 경로. 없으면 None.

    ⚠️ 경로를 코드에 박지 않는다. 소스로 실행할 때와 exe 로 묶었을 때 위치가 다르다.
       PyInstaller 는 --add-data 로 넣은 파일을 sys._MEIPASS 아래에 푼다.
    """
    bases = []
    meipass = getattr(sys, "_MEIPASS", None)      # exe 안에서 실행 중일 때만 있다
    if meipass:
        bases.append(Path(meipass))
    # src/clap_launcher/ui/app.py → [0]=ui, [1]=clap_launcher, [2]=src, [3]=저장소 루트
    bases.append(Path(__file__).resolve().parents[3])

    for base in bases:
        candidate = base / "assets" / "icon.ico"
        if candidate.is_file():
            return candidate
    return None


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

    def __init__(self, settings: Settings | None = None,
                 start_minimized: bool = False) -> None:
        """
        Args:
            start_minimized: 창을 띄우지 않고 트레이에서 시작할지.
                             (Windows 로그인 시 자동 실행되는 경로에서 쓴다)
        """
        super().__init__()
        self.settings = settings if settings is not None else load_settings()
        self.monitor = AudioMonitor()
        self.current_page: ttk.Frame | None = None
        self._closed = False   # 정리를 두 번 하지 않기 위한 표시
        self._lock_watcher = LockWatcher()
        self.tray = TrayIcon(on_show=self.show_window,
                             on_toggle_listening=self.toggle_listening,
                             on_quit=self.quit_app)

        # ⚠️ 화면 배율은 **화면을 만들기 전에** 정해야 한다.
        #    위젯들이 만들어지는 순간의 배율로 크기를 잡기 때문이다.
        theme.init_scaling(self)

        self.title(WINDOW_TITLE)
        self._apply_window_icon()
        width, height = theme.px(WINDOW_WIDTH), theme.px(WINDOW_HEIGHT)
        self.geometry(f"{width}x{height}")
        self.minsize(width - theme.px(20), height - theme.px(40))
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

        # 트레이가 있어야 '창을 닫아도 계속 돈다'가 성립한다.
        # 없으면(라이브러리 미설치·원격 세션 등) 창을 닫을 때 그냥 종료한다.
        self.tray.start(listening=False)

        if start_minimized and self.tray.available:
            self.withdraw()          # 로그인 직후 창이 튀어나오지 않게
        else:
            self._bring_to_front()

        self.after(UI_REFRESH_MS, self._tick)
        self.after(LOCK_POLL_MS, self._check_session_lock)

    def _apply_window_icon(self) -> None:
        """제목 표시줄·작업표시줄·Alt+Tab 에 쓰이는 창 아이콘을 지정한다.

        파일(assets/icon.ico)이 있으면 그걸 쓰고, 없으면 그 자리에서 그려서 쓴다.
        exe 로 묶었을 때 파일이 빠지는 사고가 흔해서 **그림으로 물러설 길**을 남겨둔다.
        (아이콘이 없다고 창이 안 뜨면 안 되므로 실패는 전부 조용히 넘어간다)
        """
        icon_file = app_icon_path()
        if icon_file is not None:
            try:
                self.iconbitmap(default=str(icon_file))
                return
            except tk.TclError:
                pass

        try:
            from PIL import ImageTk

            image = icons.render_badge(64, fill=theme.ACCENT, fill_bottom=theme.ACCENT_DARK)
            if image is None:
                return
            # 참조를 들고 있어야 한다. 놓으면 가비지 컬렉션돼 아이콘이 사라진다.
            self._icon_photo = ImageTk.PhotoImage(image)
            self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

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

        # 입력칸: 뉴모피즘답게 '움푹 들어간 바닥'처럼 보이도록 테두리를 없애고 배경만 낮춘다.
        # (진짜 그림자를 주려면 캔버스로 만들어야 하는데, 글자 입력 기능을 다시 만들어야 해서
        #  얻는 것보다 잃는 게 많다. 색만으로 충분히 '입력하는 곳'으로 읽힌다)
        style.configure("Neo.TEntry", fieldbackground=theme.BG_SUNKEN,
                        foreground=theme.FG, bordercolor=theme.DARK,
                        lightcolor=theme.BG_SUNKEN, darkcolor=theme.BG_SUNKEN,
                        borderwidth=1, relief="flat", padding=theme.px(5))
        style.map("Neo.TEntry", bordercolor=[("focus", theme.ACCENT)])

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
                                 on_calibrate=self.show_calibrate_page,
                                 on_edit_apps=self.show_apps_page))

    def show_apps_page(self) -> None:
        """실행할 프로그램 목록 편집 화면. 이 화면은 마이크를 쓰지 않는다."""
        self.monitor.stop()
        self._swap_page(AppsPage(self.container, on_done=self.show_main_page))

    def show_calibrate_page(self) -> None:
        self._swap_page(CalibratePage(self.container, self.monitor, self.settings,
                                      on_done=self.show_main_page))

    # ── 주기적 갱신 ────────────────────────────────────────
    def _tick(self) -> None:
        """50ms마다 현재 화면에게 '최신 값으로 갱신하라'고 알린다.

        오디오 스레드가 화면을 직접 건드리면 안 되므로, 화면 쪽에서 읽어가는 방식을 쓴다.
        (Tkinter 위젯은 메인 스레드에서만 만질 수 있다)

        트레이 메뉴에서 온 요청도 여기서 처리한다. 같은 이유다 —
        트레이 스레드가 창을 직접 건드리면 안 된다.
        """
        self.tray.process_pending()

        page = self.current_page
        if page is not None and hasattr(page, "update_from_monitor"):
            try:
                page.update_from_monitor()
            except tk.TclError:
                return   # 창이 닫히는 중이면 조용히 멈춘다

        self.tray.set_listening(self.is_listening())
        self.after(UI_REFRESH_MS, self._tick)

    # ── 트레이에서 오는 요청 (전부 화면 스레드에서 실행된다) ──
    def is_listening(self) -> bool:
        """지금 마이크를 열고 있는가. 트레이 아이콘 색을 정하는 데 쓴다."""
        page = self.current_page
        session = getattr(page, "session", None)
        return bool(session is not None and session.armed)

    def show_window(self) -> None:
        """트레이에서 '창 열기'. 숨겨둔 창을 다시 보여준다."""
        if self._closed:
            return
        try:
            self.deiconify()
            self._bring_to_front()
        except tk.TclError:
            pass

    def toggle_listening(self) -> None:
        """트레이에서 '듣기 시작/중지'.

        메인 화면이 듣기 상태를 관리하므로 그쪽에 넘긴다. 다른 화면(설정·보정)에
        있을 때는 넘길 곳이 없으므로 창을 열어 사용자가 직접 하게 한다.
        """
        page = self.current_page
        if hasattr(page, "_toggle_listening"):
            try:
                page._toggle_listening()
                return
            except tk.TclError:
                return
        self.show_window()

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
        """창의 X 버튼을 눌렀을 때.

        트레이가 살아 있으면 **종료하지 않고 숨긴다.** 잠금을 풀 때 알아서 켜지는 게
        이 프로그램의 쓸모인데, 창을 닫았다고 죽어버리면 그 쓸모가 사라진다.
        완전히 끄는 길은 트레이 메뉴의 '종료'다.
        """
        if self._closed:
            return
        if self.settings.minimize_to_tray and self.tray.running:
            self.hide_to_tray()
            return
        self.quit_app()

    def hide_to_tray(self) -> None:
        """창만 숨긴다. 감지는 계속 돌아간다."""
        try:
            self.withdraw()
        except tk.TclError:
            return

        # 처음 한 번은 어디로 갔는지 알려준다. 안 그러면 '꺼졌나?' 하고 또 실행하게 된다.
        if not self.settings.tray_notice_shown:
            self.settings.tray_notice_shown = True
            try:
                save_settings(self.settings)
            except OSError:
                pass       # 저장 실패는 이번 실행에만 영향을 준다
            self.tray.notify("트레이에서 계속 실행 중입니다.\n"
                             "완전히 끄려면 트레이 아이콘 → 종료를 누르세요.")

    def quit_app(self) -> None:
        """완전히 종료한다. 오디오 스레드와 트레이를 확실히 정리하고 나간다.

        여러 번 불려도 안전해야 한다: 사용자가 종료를 누른 뒤에도 마무리 정리(finally)에서
        한 번 더 부르기 때문이다. 이미 닫힌 창에 destroy()를 부르면 오류가 난다.
        """
        if self._closed:
            return
        self._closed = True
        self.monitor.stop()
        self.tray.stop()
        try:
            self.destroy()
        except tk.TclError:
            pass   # 이미 창이 사라진 상태 — 정상적인 종료 경로다


def run_gui(start_minimized: bool = False) -> int:
    """GUI를 띄운다. 종료 코드를 반환한다.

    Args:
        start_minimized: 창 없이 트레이에서 시작할지 (로그인 자동 실행용).
    """
    # GUI라도 오류 메시지는 콘솔로 나가므로 인코딩을 먼저 맞춰둔다
    force_utf8_console()
    _enable_dpi_awareness()
    app = ClapLauncherApp(start_minimized=start_minimized)
    try:
        app.mainloop()
    except KeyboardInterrupt:
        # 터미널에서 Ctrl+C 로 끄는 것은 '오류'가 아니라 정상적인 종료 방법이다.
        # 그냥 두면 파이썬 traceback이 그대로 쏟아져서 사용자는 프로그램이 고장 난 줄 안다.
        print("\n종료합니다.")
    finally:
        # 어떻게 끝났든 마이크와 트레이는 반드시 정리한다.
        # 이걸 빠뜨리면 창은 사라졌는데 마이크를 붙잡은 프로세스가 남는다.
        # (on_close 가 아니라 quit_app 이다 — 여기서 트레이로 숨어봐야 소용없다)
        app.quit_app()
    return 0
