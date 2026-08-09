"""초기 화면 — 사용할 마이크를 고르는 화면.

이 화면이 제일 먼저 나오는 이유:
이 PC에는 입력 장치가 30개 넘게 잡힌다(가상 오디오 장치, 오디오 인터페이스, 웹캠 마이크…).
게다가 Windows 기본 장치가 실제 마이크가 아닌 경우도 흔하다.
"박수를 쳐도 반응이 없다"의 대부분이 여기서 갈리므로, 시작할 때 한 번 확실히 정하고 간다.

핵심 UX: 목록에서 고르면 **그 자리에서 바로 음량 막대가 움직인다.**
사용자는 박수를 쳐보고 막대가 튀는 걸 눈으로 확인한 다음 결정하면 된다.
"""

import tkinter as tk
from tkinter import ttk

from ..audio.listener import AudioDeviceError, list_input_devices
from ..settings import Settings, save_settings
from . import icons, theme
from .audio_monitor import AudioMonitor
from .neumorphic import IconLabel, NeoButton, NeoPanel
from .widgets import LevelMeter

PANEL_WIDTH = 520


class DevicePage(ttk.Frame):
    """마이크 선택 화면."""

    def __init__(self, parent, monitor: AudioMonitor, settings: Settings, on_done) -> None:
        """
        Args:
            monitor: 음량 측정 일꾼 (화면끼리 공유한다)
            settings: 현재 설정. 고른 마이크를 여기에 적어 저장한다.
            on_done: 선택이 끝났을 때 부를 함수 (메인 화면으로 넘어가기)
        """
        super().__init__(parent, padding=(theme.px(24), theme.px(18)))
        self.monitor = monitor
        self.settings = settings
        self.on_done = on_done
        self.devices: list[tuple[int, str]] = []

        self._build()
        self.refresh_devices()

    # ── 화면 구성 ──────────────────────────────────────────
    def _build(self) -> None:
        header = tk.Canvas(self, width=theme.px(PANEL_WIDTH), height=theme.px(40), bg=theme.BG,
                           highlightthickness=0, bd=0)
        header.pack(anchor="w")
        icons.draw(header, "mic", theme.px(16), theme.px(20), theme.px(26), theme.ACCENT, width=2)
        header.create_text(theme.px(38), theme.px(21), text="사용할 마이크를 고르세요", anchor="w",
                           fill=theme.FG, font=theme.FONT_TITLE)

        ttk.Label(
            self,
            text="목록에서 마이크를 고른 뒤 박수를 쳐보세요.\n"
                 "아래 막대가 크게 튀는 마이크가 정답입니다.",
            style="Muted.TLabel", justify="left",
        ).pack(anchor="w", pady=(theme.px(6), theme.px(10)))

        # ── 장치 목록 (30개가 넘으므로 스크롤 필요) ──
        panel = NeoPanel(self, width=PANEL_WIDTH, height=170, padding=10)
        panel.pack(anchor="w")

        scrollbar = ttk.Scrollbar(panel.body, orient="vertical")
        self.listbox = tk.Listbox(
            panel.body, activestyle="none", exportselection=False,
            bg=theme.BG_SUNKEN, fg=theme.FG, selectbackground=theme.ACCENT,
            selectforeground=theme.FG_ON_ACCENT, highlightthickness=0, bd=0,
            font=theme.FONT_BODY, yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self.listbox.yview)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        # 목록에서 고르는 즉시 그 장치로 듣기 시작한다 (별도 '미리듣기' 버튼이 필요 없게)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        hint_row = ttk.Frame(self)
        hint_row.pack(anchor="w", fill="x", pady=(theme.px(4), 0))
        NeoButton(hint_row, text="목록 새로고침", icon="refresh",
                  command=self.refresh_devices, height=32).pack(side="left")
        ttk.Label(hint_row, text="같은 마이크가 여러 번 보이는 것은 정상입니다\n"
                                 "(드라이버 방식별로 하나씩).",
                  style="Small.TLabel", justify="left").pack(side="left", padx=(theme.px(6), 0))

        # ── 실시간 확인 영역 ──
        self.spec_label = ttk.Label(self, text="마이크를 선택하세요", style="Small.TLabel")
        self.spec_label.pack(anchor="w", pady=(theme.px(10), theme.px(2)))

        meter_row = ttk.Frame(self)
        meter_row.pack(fill="x")
        self.meter = LevelMeter(meter_row)
        self.meter.pack(side="left")
        self.level_label = ttk.Label(meter_row, text="  --.- dBFS", style="Mono.TLabel")
        self.level_label.pack(side="left", padx=(theme.px(6), 0))

        self.status_label = IconLabel(self, width=PANEL_WIDTH, icon="hourglass", text="",
                                      color=theme.FG_MUTED)
        self.status_label.pack(anchor="w", pady=(theme.px(2), theme.px(4)))
        self.detail_label = ttk.Label(self, text="", style="Muted.TLabel", wraplength=theme.px(500),
                                      justify="left")
        self.detail_label.pack(anchor="w", pady=(0, theme.px(8)))

        self.confirm_button = NeoButton(self, text="이 마이크 사용하기", icon="check",
                                        command=self._confirm, accent=True)
        self.confirm_button.pack(anchor="w")
        self.confirm_button.configure_state(False)

    # ── 동작 ──────────────────────────────────────────────
    def refresh_devices(self) -> None:
        """장치 목록을 다시 읽는다. USB 마이크를 꽂았을 때 쓴다."""
        try:
            self.devices = list_input_devices()
        except Exception as exc:
            # 오디오 장치 조회 자체가 실패해도 창이 죽지는 않게 한다
            self.devices = []
            self.status_label.set("장치 목록을 읽지 못했습니다", "warning", theme.ERROR)
            self.detail_label.config(text=str(exc), foreground=theme.ERROR)
            return

        self.listbox.delete(0, tk.END)
        for index, name in self.devices:
            self.listbox.insert(tk.END, f" [{index:3d}]  {name}")

        if not self.devices:
            self.status_label.set("입력 장치를 찾지 못했습니다", "warning", theme.ERROR)
            self.detail_label.config(text="마이크가 연결돼 있는지 확인해 주세요.",
                                     foreground=theme.ERROR)
            return

        # 예전에 고른 장치가 있으면 그 자리를 미리 선택해 준다
        previous = self.settings.device
        preselect = 0
        for row, (index, name) in enumerate(self.devices):
            if previous == index or (isinstance(previous, str) and previous.lower() in name.lower()):
                preselect = row
                break

        self.listbox.selection_set(preselect)
        self.listbox.see(preselect)
        self._start_preview(preselect)

    def _on_select(self, event=None) -> None:
        selection = self.listbox.curselection()
        if selection:
            self._start_preview(selection[0])

    def _start_preview(self, row: int) -> None:
        """고른 장치로 음량 측정을 시작한다."""
        if not (0 <= row < len(self.devices)):
            return
        index, name = self.devices[row]
        self.confirm_button.configure_state(False)
        self.status_label.set("마이크를 여는 중…", "hourglass", theme.FG_MUTED)
        self.detail_label.config(text="")
        self.spec_label.config(text=f"선택: [{index}] {name}")
        try:
            self.monitor.start(index)
        except AudioDeviceError as exc:
            self.status_label.set("마이크를 열지 못했습니다", "warning", theme.ERROR)
            self.detail_label.config(text=str(exc), foreground=theme.ERROR)

    def update_from_monitor(self) -> None:
        """창이 주기적으로 불러준다. 최신 측정값을 화면에 반영한다.

        (오디오 스레드가 직접 위젯을 건드리면 안 되므로 이렇게 '읽어가는' 방식을 쓴다)
        """
        snapshot = self.monitor.snapshot()
        self.meter.set_level(snapshot.level_dbfs, snapshot.peak_dbfs)
        self.level_label.config(text=f"{snapshot.level_dbfs:7.1f} dBFS")

        if snapshot.error:
            self.status_label.set("마이크 오류", "warning", theme.ERROR)
            self.detail_label.config(text=snapshot.error, foreground=theme.ERROR)
            self.confirm_button.configure_state(False)
            return

        if snapshot.device_desc:
            self.spec_label.config(text=f"열린 장치: {snapshot.device_desc}")

        if snapshot.is_loud_enough:
            # 소리가 확실히 잡힌 마이크만 '사용하기'를 열어준다.
            # 무음만 들어오는 가상 장치를 고르고 넘어가는 사고를 여기서 막는다.
            self.status_label.set("소리가 잘 잡힙니다. 이 마이크를 쓰면 됩니다.",
                                  "check", theme.OK)
            self.detail_label.config(text="")
            self.confirm_button.configure_state(True)
        elif snapshot.running:
            self.status_label.set("아직 큰 소리가 잡히지 않았습니다. 박수를 쳐보세요.",
                                  "hourglass", theme.WARN)

    def _confirm(self) -> None:
        """고른 마이크를 저장하고 메인 화면으로 넘어간다."""
        selection = self.listbox.curselection()
        if not selection:
            return
        index, name = self.devices[selection[0]]

        self.settings.device = index
        self.settings.device_label = name
        self.settings.setup_done = True
        try:
            save_settings(self.settings)
        except OSError as exc:
            # 저장에 실패해도 이번 실행은 계속 쓸 수 있어야 한다. 다음 실행 때 다시 고르면 된다.
            self.status_label.set("설정을 저장하지 못했습니다", "warning", theme.WARN)
            self.detail_label.config(text=f"{exc}\n이번 실행에만 적용됩니다.",
                                     foreground=theme.WARN)
        self.on_done()
