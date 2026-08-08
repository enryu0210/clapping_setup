"""메인 화면 — 마이크 선택을 끝낸 뒤 평소에 보게 되는 화면.

지금(M1)은 "듣고 있다"는 것과 음량만 보여준다.
박수 감지(M3)와 프로그램 실행(M4)이 붙으면 이 화면에 감지 횟수와 실행 결과가 추가된다.

⚠️ 화면에 상태를 항상 보여주는 것은 단순한 장식이 아니다.
마이크를 계속 듣는 프로그램이 아무 흔적도 없이 돌면 사용자가 불안해진다.
'지금 듣는 중 / 멈춤'을 눈에 보이게 하는 것이 프라이버시에 대한 가장 현실적인 대응이다.
"""

from tkinter import ttk

from . import widgets as w
from .audio_monitor import AudioMonitor


class MainPage(ttk.Frame):
    """상태 표시 + 음량 미터 화면."""

    def __init__(self, parent, monitor: AudioMonitor, settings, on_change_device) -> None:
        super().__init__(parent, padding=20)
        self.monitor = monitor
        self.settings = settings
        self.on_change_device = on_change_device
        self.listening = True   # 일시정지 여부. 회의 중에는 끌 수 있어야 한다.

        self._build()

    def _build(self) -> None:
        ttk.Label(self, text="👏 Clapping Setup", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self, text="박수 두 번이면 일할 준비 끝.", style="Muted.TLabel"
        ).pack(anchor="w", pady=(4, 16))

        # ── 현재 상태 ──
        self.status_label = ttk.Label(self, text="● 듣는 중", style="Status.TLabel")
        self.status_label.pack(anchor="w")
        self.device_label = ttk.Label(
            self, text=f"마이크: {self.settings.device_label or '기본 장치'}",
            style="Small.TLabel",
        )
        self.device_label.pack(anchor="w", pady=(2, 12))

        # ── 음량 미터 ──
        meter_row = ttk.Frame(self)
        meter_row.pack(fill="x")
        self.meter = w.LevelMeter(meter_row)
        self.meter.pack(side="left")
        self.level_label = ttk.Label(meter_row, text="  --.- dBFS", style="Mono.TLabel")
        self.level_label.pack(side="left", padx=(10, 0))

        self.error_label = ttk.Label(self, text="", style="Muted.TLabel", wraplength=500)
        self.error_label.pack(anchor="w", pady=(6, 0))

        # ── 아직 구현 전인 부분을 솔직하게 알린다 ──
        notice = ttk.LabelFrame(self, text=" 진행 상황 ", padding=12)
        notice.pack(fill="x", pady=(20, 12))
        ttk.Label(
            notice,
            text="지금은 마이크 음량만 표시합니다.\n"
                 "다음 단계에서 박수 감지(M2~M3)와 프로그램 실행(M4)이 연결됩니다.",
            style="Small.TLabel", justify="left",
        ).pack(anchor="w")

        # ── 버튼 ──
        button_row = ttk.Frame(self)
        button_row.pack(fill="x", pady=(4, 0))
        self.toggle_button = ttk.Button(
            button_row, text="⏸ 일시정지", command=self._toggle_listening, style="Accent.TButton"
        )
        self.toggle_button.pack(side="left")
        ttk.Button(button_row, text="🎤 마이크 변경", command=self.on_change_device).pack(
            side="left", padx=(8, 0)
        )

    def _toggle_listening(self) -> None:
        """듣기를 켜고 끈다. 화상회의 중에 마이크를 양보하려면 필요하다."""
        self.listening = not self.listening
        if self.listening:
            self.monitor.start(self.settings.device)
            self.toggle_button.config(text="⏸ 일시정지")
            self.status_label.config(text="● 듣는 중", foreground=w.OK)
        else:
            self.monitor.stop()
            self.toggle_button.config(text="▶ 다시 듣기")
            self.status_label.config(text="■ 멈춤", foreground=w.FG_MUTED)
            self.meter.set_level(w.METER_MIN_DBFS, w.METER_MIN_DBFS)
            self.level_label.config(text="   --.- dBFS")

    def update_from_monitor(self) -> None:
        """창이 주기적으로 불러준다. 최신 측정값을 화면에 반영한다."""
        if not self.listening:
            return

        snapshot = self.monitor.snapshot()
        self.meter.set_level(snapshot.level_dbfs, snapshot.peak_dbfs)
        self.level_label.config(text=f"{snapshot.level_dbfs:7.1f} dBFS")

        if snapshot.error:
            self.status_label.config(text="● 오류", foreground=w.ERROR)
            self.error_label.config(
                text=f"❌ {snapshot.error}\n'마이크 변경'에서 다른 장치를 골라보세요.",
                foreground=w.ERROR,
            )
        else:
            self.error_label.config(text="")
            self.status_label.config(text="● 듣는 중", foreground=w.OK)
