"""시스템 트레이 아이콘 — 창을 닫아도 뒤에서 계속 대기한다.

왜 필요한가:
이 프로그램의 쓸모는 "잠금을 풀면 알아서 준비된다"인데, 그러려면 항상 떠 있어야 한다.
그렇다고 창을 계속 띄워두면 작업표시줄만 차지한다. 그래서 창을 닫으면 트레이로 내려간다.

**아이콘 색이 곧 상태 표시다.** 마이크를 듣는 프로그램이 화면에 아무 흔적도 없으면
사용자가 불안하다. 이건 장식이 아니라 프라이버시에 대한 대응이다.
  초록 = 듣는 중 (마이크를 열고 있다)
  회색 = 대기 중 (마이크를 아예 잡지 않는다)

⚠️ 스레드 조심 — 이 파일에서 가장 중요한 부분:
pystray 는 **자기 루프를 따로 돈다.** 메뉴를 누르면 그 콜백이 트레이 스레드에서 불린다.
거기서 Tkinter 위젯을 건드리면 프로그램이 이유 없이 멈추거나 죽는다.
(audio_monitor.py 와 똑같은 함정이다)

그래서 트레이 스레드는 **할 일을 큐에 넣기만 하고**, 실제 실행은 화면 스레드가
주기적으로 큐를 비우면서 한다. 큐를 쓴 덕분에 pystray 없이도 테스트할 수 있다.
"""

import queue
import threading

from . import icons, theme

try:
    import pystray
    _HAS_PYSTRAY = True
except ImportError:      # pystray 가 없어도 프로그램은 창 모드로 정상 동작해야 한다
    _HAS_PYSTRAY = False

ICON_SIZE = 64           # 트레이 아이콘 원본 크기. Windows 가 알아서 줄여서 쓴다


# ── 화면·라이브러리와 상관없는 계산 (창 없이 테스트할 수 있게 밖으로 뺐다) ──

def toggle_label(listening: bool) -> str:
    """메뉴에 보여줄 글자. 지금 상태가 아니라 **누르면 일어날 일**을 적는다."""
    return "듣기 중지" if listening else "듣기 시작"


def status_text(listening: bool) -> str:
    """아이콘에 마우스를 올렸을 때 뜨는 설명."""
    state = "듣는 중" if listening else "대기 중 (마이크 사용 안 함)"
    return f"Clapping Setup — {state}"


def status_color(listening: bool) -> str:
    """아이콘 색. 듣고 있을 때만 눈에 띄어야 한다."""
    return theme.OK if listening else theme.FG_MUTED


def make_icon_image(listening: bool, size: int = ICON_SIZE):
    """트레이에 올릴 아이콘 이미지를 만든다.

    메인 화면과 같은 박수 아이콘을 쓴다 — 작업표시줄에서도 같은 프로그램으로 알아보게.

    Returns:
        Pillow 이미지. Pillow 가 없으면 None (그때는 트레이 기능을 포기한다).
    """
    return icons.render_image("clap", size, status_color(listening), width=4)


class TrayIcon:
    """트레이 아이콘 하나.

    pystray 나 Pillow 가 없으면 **아무것도 하지 않는다.** 트레이는 편의 기능이므로,
    없다고 프로그램이 안 뜨면 안 된다. start() 가 False 를 돌려주면 부르는 쪽에서
    '창을 닫으면 그냥 종료' 로 동작을 바꾼다.
    """

    def __init__(self, on_show, on_toggle_listening, on_quit) -> None:
        """
        Args:
            on_show: 창 열기를 눌렀을 때 (화면 스레드에서 불린다)
            on_toggle_listening: 듣기 시작/중지를 눌렀을 때
            on_quit: 종료를 눌렀을 때
        """
        self._on_show = on_show
        self._on_toggle = on_toggle_listening
        self._on_quit = on_quit

        self._listening = False
        self._icon = None
        self._thread: threading.Thread | None = None
        # 트레이 스레드 → 화면 스레드로 할 일을 넘기는 통로
        self._pending: queue.Queue = queue.Queue()

    @property
    def available(self) -> bool:
        """이 기기에서 트레이를 쓸 수 있는가 (라이브러리가 갖춰져 있는가)."""
        return _HAS_PYSTRAY and make_icon_image(False) is not None

    @property
    def running(self) -> bool:
        """지금 트레이 아이콘이 실제로 떠 있는가.

        available 과 구분해야 한다. 라이브러리는 있는데 띄우기에 실패하는 환경
        (원격 데스크톱 등)이 있고, 그때 창을 숨기면 프로그램이 통째로 사라진다.
        """
        return self._icon is not None

    def notify(self, message: str, title: str = "Clapping Setup") -> None:
        """풍선 알림. 창이 트레이로 내려갔다는 것을 처음 한 번 알리는 데 쓴다."""
        if self._icon is None:
            return
        try:
            self._icon.notify(message, title)
        except Exception:
            pass      # 알림을 지원하지 않는 환경도 있다. 없어도 기능에는 지장이 없다

    # ── 트레이 스레드 ↔ 화면 스레드 ────────────────────────
    def _hand_over(self, action) -> None:
        """트레이 스레드에서 불린다. **여기서는 화면을 절대 건드리지 않는다.**"""
        self._pending.put(action)

    def process_pending(self) -> int:
        """화면 스레드가 주기적으로 불러 밀린 일을 처리한다.

        Returns:
            처리한 개수 (테스트에서 확인용)
        """
        done = 0
        while True:
            try:
                action = self._pending.get_nowait()
            except queue.Empty:
                return done
            try:
                action()
            except Exception:
                # 메뉴 하나가 실패해도 나머지 처리는 계속돼야 한다
                pass
            done += 1

    # ── 켜기 / 끄기 ────────────────────────────────────────
    def start(self, listening: bool = False) -> bool:
        """트레이 아이콘을 띄운다.

        Returns:
            띄웠으면 True. 라이브러리가 없거나 실패하면 False.
        """
        if not self.available or self._icon is not None:
            return False

        self._listening = listening
        menu = pystray.Menu(
            # default=True: 아이콘을 두 번 누르면 이 항목이 실행된다 (창 열기)
            pystray.MenuItem("창 열기", lambda *_a: self._hand_over(self._on_show),
                             default=True),
            pystray.MenuItem(lambda _item: toggle_label(self._listening),
                             lambda *_a: self._hand_over(self._on_toggle)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("종료", lambda *_a: self._hand_over(self._on_quit)),
        )

        try:
            self._icon = pystray.Icon("clapping_setup", make_icon_image(listening),
                                      status_text(listening), menu)
            # daemon=True : 창을 강제로 닫아도 이 스레드가 프로그램을 붙잡지 않게
            self._thread = threading.Thread(target=self._icon.run, daemon=True,
                                            name="tray-icon")
            self._thread.start()
        except Exception:
            self._icon = None      # 트레이가 없는 환경(원격 세션 등)일 수 있다
            return False
        return True

    def set_listening(self, listening: bool) -> None:
        """상태가 바뀌면 아이콘 색과 설명을 갱신한다."""
        if self._listening == listening:
            return
        self._listening = listening
        if self._icon is None:
            return
        try:
            self._icon.icon = make_icon_image(listening)
            self._icon.title = status_text(listening)
            self._icon.update_menu()     # '듣기 시작/중지' 글자도 함께 바뀐다
        except Exception:
            pass      # 아이콘 갱신 실패로 프로그램이 죽을 이유는 없다

    def stop(self) -> None:
        """트레이 아이콘을 내린다. 여러 번 불러도 안전하다."""
        icon, self._icon = self._icon, None
        if icon is None:
            return
        try:
            icon.stop()
        except Exception:
            pass
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
