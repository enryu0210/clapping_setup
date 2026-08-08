"""메인 화면 — 마이크 선택을 끝낸 뒤 평소에 보게 되는 화면.

박수 감지 상태와 **무엇을 왜 걸렀는지**를 실시간으로 보여준다.
걸러진 이유까지 보여주는 게 중요하다. "왜 안 잡히지?"를 화면만 보고 알 수 있어야
사용자가 스스로 보정하거나 마이크를 바꿔볼 수 있다.

⚠️ 화면에 상태를 항상 보여주는 것은 단순한 장식이 아니다.
마이크를 계속 듣는 프로그램이 아무 흔적도 없이 돌면 사용자가 불안해진다.
'지금 듣는 중 / 멈춤'을 눈에 보이게 하는 것이 프라이버시에 대한 가장 현실적인 대응이다.
"""

import time
import tkinter as tk
from tkinter import ttk

from ..config import DetectionConfig
from . import widgets as w
from .audio_monitor import AudioMonitor

TRIGGER_FLASH_SEC = 3.0   # 발동 후 몇 초간 크게 표시할지


class MainPage(ttk.Frame):
    """상태 표시 + 음량 미터 + 감지 로그 화면."""

    def __init__(self, parent, monitor: AudioMonitor, settings,
                 on_change_device, on_calibrate) -> None:
        super().__init__(parent, padding=20)
        self.monitor = monitor
        self.settings = settings
        self.on_change_device = on_change_device
        self.on_calibrate = on_calibrate
        self.listening = True     # 일시정지 여부. 회의 중에는 끌 수 있어야 한다.
        self._shown_events = 0    # 로그에 이미 그린 이벤트 개수

        self._build()

    def _build(self) -> None:
        ttk.Label(self, text="👏 Clapping Setup", style="Title.TLabel").pack(anchor="w")

        # ── 현재 상태 ──
        self.status_label = ttk.Label(self, text="● 듣는 중", style="Status.TLabel")
        self.status_label.pack(anchor="w", pady=(8, 0))
        self.device_label = ttk.Label(
            self, text=self._device_text(), style="Small.TLabel",
        )
        self.device_label.pack(anchor="w", pady=(2, 10))

        # ── 음량 미터 ──
        meter_row = ttk.Frame(self)
        meter_row.pack(fill="x")
        self.meter = w.LevelMeter(meter_row)
        self.meter.pack(side="left")
        self.level_label = ttk.Label(meter_row, text="  --.- dBFS", style="Mono.TLabel")
        self.level_label.pack(side="left", padx=(10, 0))

        # ── 감지 결과 ──
        self.detect_label = ttk.Label(self, text="박수 두 번(짝짝)을 기다리는 중…",
                                      style="Muted.TLabel")
        self.detect_label.pack(anchor="w", pady=(14, 6))

        log_box = ttk.LabelFrame(self, text=" 들린 소리 (걸러진 것 포함) ", padding=8)
        log_box.pack(fill="both", expand=True)
        self.log = tk.Listbox(
            log_box, height=8, activestyle="none",
            bg=w.BG_PANEL, fg=w.FG_MUTED, highlightthickness=0, bd=0, font=w.FONT_MONO,
            selectbackground=w.BG_PANEL, selectforeground=w.FG,
        )
        self.log.pack(fill="both", expand=True)

        self.error_label = ttk.Label(self, text="", style="Muted.TLabel", wraplength=500)
        self.error_label.pack(anchor="w", pady=(6, 0))

        # ── 버튼 ──
        button_row = ttk.Frame(self)
        button_row.pack(fill="x", pady=(12, 0))
        self.toggle_button = ttk.Button(
            button_row, text="⏸ 일시정지", command=self._toggle_listening, style="Accent.TButton"
        )
        self.toggle_button.pack(side="left")
        ttk.Button(button_row, text="🎯 박수 보정", command=self.on_calibrate).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(button_row, text="🎤 마이크 변경", command=self.on_change_device).pack(
            side="left", padx=(8, 0)
        )

    def _device_text(self) -> str:
        mic = self.settings.device_label or "기본 장치"
        tuned = "보정됨" if self.settings.detection else "기본 기준값"
        return f"마이크: {mic}  ·  {tuned}"

    def _toggle_listening(self) -> None:
        """듣기를 켜고 끈다. 화상회의 중에 마이크를 양보하려면 필요하다."""
        self.listening = not self.listening
        if self.listening:
            self.monitor.start(self.settings.device, self._detection_config())
            self._shown_events = 0
            self.toggle_button.config(text="⏸ 일시정지")
            self.status_label.config(text="● 듣는 중", foreground=w.OK)
        else:
            self.monitor.stop()
            self.toggle_button.config(text="▶ 다시 듣기")
            self.status_label.config(text="■ 멈춤", foreground=w.FG_MUTED)
            self.meter.set_level(w.METER_MIN_DBFS, w.METER_MIN_DBFS)
            self.level_label.config(text="   --.- dBFS")

    def _detection_config(self) -> DetectionConfig:
        """보정한 기준값이 있으면 그것을, 없으면 기본값을 쓴다."""
        return DetectionConfig.from_dict(self.settings.detection or {})

    def update_from_monitor(self) -> None:
        """창이 주기적으로 불러준다. 최신 측정값과 감지 결과를 화면에 반영한다."""
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
            return

        self.error_label.config(text="")
        self.status_label.config(text="● 듣는 중", foreground=w.OK)
        self._update_log(snapshot)
        self._update_detect_label(snapshot)

    def _update_log(self, snapshot) -> None:
        """새로 들어온 소리만 로그에 덧붙인다 (매번 전체를 다시 그리면 깜빡인다)."""
        for event in snapshot.events[self._shown_events:]:
            if event.triggered:
                text = "🎉 짝짝! 발동"
            elif event.is_clap:
                text = f"👏 박수 1회  {event.features.describe()}"
            else:
                text = f"·  {event.reject_reason}"
            self.log.insert(tk.END, f" {text}")
            self.log.see(tk.END)
        self._shown_events = len(snapshot.events)

        # 목록이 무한정 길어지지 않게 오래된 줄을 지운다
        while self.log.size() > 200:
            self.log.delete(0)

    def _update_detect_label(self, snapshot) -> None:
        recent = snapshot.last_trigger_at and (
            time.monotonic() - snapshot.last_trigger_at < TRIGGER_FLASH_SEC
        )
        if recent:
            self.detect_label.config(text="🎉 박수 감지! (프로그램 실행은 M4에서 연결)",
                                     foreground=w.OK)
        else:
            self.detect_label.config(
                text=f"박수 두 번(짝짝)을 기다리는 중…   지금까지 {snapshot.trigger_count}회 감지",
                foreground=w.FG_MUTED,
            )
