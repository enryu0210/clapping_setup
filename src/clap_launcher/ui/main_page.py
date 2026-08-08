"""메인 화면 — 평소에 보게 되는 화면.

⚠️ 이 화면의 핵심 개념은 **'듣는 중'과 '대기 중'** 이다.

박수 감지를 아무리 정교하게 만들어도 하루 8시간을 듣고 있으면 오탐은 언젠가 난다.
확률 싸움에서 이길 수 없다. 그래서 "얼마나 정확하게 듣느냐"가 아니라
**"언제 듣느냐"** 를 제한하는 쪽으로 설계를 바꿨다.

  듣는 중 : 화면 잠금이 풀린 직후 / 사용자가 직접 켰을 때. 정해진 시간이 지나면 자동 종료.
  대기 중 : 마이크를 **아예 열지 않는다.** 오탐도, 화상회의 충돌도, 프라이버시 걱정도 없다.

박수를 감지해 할 일을 마치면 곧바로 대기 중으로 돌아간다.
자세한 배경은 listening.py, 잠금 감지는 session_lock.py 참고.
"""

import time
import tkinter as tk
from tkinter import ttk

from ..config import DetectionConfig
from ..listening import ListeningSession, StopReason, format_remaining
from ..settings import save_settings
from . import widgets as w
from .audio_monitor import AudioMonitor, take_new_events

TIMEOUT_CHOICES = ("0", "1", "3", "5", "10", "15", "30")

STOP_MESSAGES = {
    StopReason.NEVER_STARTED: "듣기를 시작하면 박수를 기다립니다.",
    StopReason.TRIGGERED: "🎉 박수를 감지해서 실행했습니다.",
    StopReason.TIMED_OUT: "⏱ 정해진 시간 동안 박수가 없어 멈췄습니다.",
    StopReason.MANUAL: "직접 멈췄습니다.",
}


class MainPage(ttk.Frame):
    """듣기 상태 관리 + 감지 로그 화면."""

    def __init__(self, parent, monitor: AudioMonitor, settings,
                 on_change_device, on_calibrate) -> None:
        super().__init__(parent, padding=20)
        self.monitor = monitor
        self.settings = settings
        self.on_change_device = on_change_device
        self.on_calibrate = on_calibrate

        self.session = ListeningSession()
        self._shown_events = 0    # 로그에 이미 그린 이벤트의 누적 개수

        self._build()
        # 프로그램을 방금 켰다는 것은 쓰겠다는 뜻이므로 바로 듣기 시작한다
        self.start_listening()

    # ── 화면 구성 ──────────────────────────────────────────
    def _build(self) -> None:
        ttk.Label(self, text="👏 Clapping Setup", style="Title.TLabel").pack(anchor="w")

        self.status_label = ttk.Label(self, text="", style="Status.TLabel")
        self.status_label.pack(anchor="w", pady=(10, 0))
        self.reason_label = ttk.Label(self, text="", style="Muted.TLabel", wraplength=520)
        self.reason_label.pack(anchor="w", pady=(2, 2))
        self.device_label = ttk.Label(self, text=self._device_text(), style="Small.TLabel")
        self.device_label.pack(anchor="w", pady=(2, 10))

        # ── 음량 미터 ──
        meter_row = ttk.Frame(self)
        meter_row.pack(fill="x")
        self.meter = w.LevelMeter(meter_row)
        self.meter.pack(side="left")
        self.level_label = ttk.Label(meter_row, text="  --.- dBFS", style="Mono.TLabel")
        self.level_label.pack(side="left", padx=(10, 0))

        # ── 감지 로그 ──
        log_box = ttk.LabelFrame(self, text=" 들린 소리 (걸러진 것 포함) ", padding=8)
        log_box.pack(fill="both", expand=True, pady=(12, 10))
        self.log = tk.Listbox(
            log_box, height=7, activestyle="none",
            bg=w.BG_PANEL, fg=w.FG_MUTED, highlightthickness=0, bd=0, font=w.FONT_MONO,
            selectbackground=w.BG_PANEL, selectforeground=w.FG,
        )
        self.log.pack(fill="both", expand=True)

        self.error_label = ttk.Label(self, text="", style="Muted.TLabel", wraplength=520)
        self.error_label.pack(anchor="w")

        self._build_options()
        self._build_buttons()

    def _build_options(self) -> None:
        """언제 들을지에 대한 설정 두 가지."""
        options = ttk.Frame(self)
        options.pack(fill="x", pady=(6, 10))

        self.auto_arm_var = tk.BooleanVar(value=self.settings.auto_arm_on_unlock)
        ttk.Checkbutton(
            options, text="화면 잠금을 풀면 자동으로 듣기 시작",
            variable=self.auto_arm_var, command=self._save_options,
        ).pack(anchor="w")

        row = ttk.Frame(options)
        row.pack(anchor="w", pady=(6, 0))
        ttk.Label(row, text="듣는 시간", style="Small.TLabel").pack(side="left")
        self.timeout_var = tk.StringVar(value=str(int(self.settings.listen_timeout_min)))
        ttk.Spinbox(
            row, values=TIMEOUT_CHOICES, textvariable=self.timeout_var, width=4,
            command=self._save_options, state="readonly",
        ).pack(side="left", padx=6)
        ttk.Label(row, text="분  (0 = 무제한)", style="Small.TLabel").pack(side="left")

    def _build_buttons(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x")
        self.toggle_button = ttk.Button(row, text="", command=self._toggle_listening,
                                        style="Accent.TButton")
        self.toggle_button.pack(side="left")
        ttk.Button(row, text="🎯 박수 보정", command=self.on_calibrate).pack(
            side="left", padx=(8, 0))
        ttk.Button(row, text="🎤 마이크 변경", command=self.on_change_device).pack(
            side="left", padx=(8, 0))

    def _device_text(self) -> str:
        mic = self.settings.device_label or "기본 장치"
        tuned = "보정됨" if self.settings.detection else "기본 기준값"
        return f"마이크: {mic}  ·  {tuned}"

    def _save_options(self) -> None:
        """설정을 바꾸면 바로 저장한다. 다음 실행에도 유지되어야 하기 때문이다."""
        self.settings.auto_arm_on_unlock = self.auto_arm_var.get()
        try:
            self.settings.listen_timeout_min = float(self.timeout_var.get())
        except ValueError:
            self.settings.listen_timeout_min = 5.0
        try:
            save_settings(self.settings)
        except OSError:
            pass   # 저장 실패는 이번 실행에 영향이 없다. 굳이 화면을 어지럽히지 않는다.

    # ── 듣기 시작 / 중지 ──────────────────────────────────
    def start_listening(self) -> None:
        """마이크를 열고 박수를 기다린다."""
        self.session.arm(time.monotonic(), self.settings.listen_timeout_min)
        self._shown_events = 0
        self.log.delete(0, tk.END)
        self.monitor.start(self.settings.device,
                           DetectionConfig.from_dict(self.settings.detection or {}))
        self._refresh_status()

    def stop_listening(self, reason: StopReason) -> None:
        """마이크를 닫는다. 대기 중에는 마이크를 아예 잡지 않는다."""
        self.session.disarm(reason)
        self.monitor.stop()
        self.meter.set_level(w.METER_MIN_DBFS, w.METER_MIN_DBFS)
        self.level_label.config(text="   --.- dBFS")
        self._refresh_status()

    def _toggle_listening(self) -> None:
        if self.session.armed:
            self.stop_listening(StopReason.MANUAL)
        else:
            self.start_listening()

    def on_session_unlocked(self) -> None:
        """창이 '화면 잠금이 방금 풀렸다'고 알려줄 때 호출된다.

        자리에 돌아와 컴퓨터를 켜는 순간 = 업무 프로그램을 띄우고 싶은 바로 그 순간이다.
        """
        if not self.settings.auto_arm_on_unlock or self.session.armed:
            return
        self.start_listening()
        self.reason_label.config(text="🔓 화면 잠금이 풀려서 듣기를 시작했습니다.",
                                 foreground=w.ACCENT)

    # ── 주기적 갱신 ────────────────────────────────────────
    def update_from_monitor(self) -> None:
        """창이 주기적으로 불러준다."""
        now = time.monotonic()

        if self.session.is_expired(now):
            self.stop_listening(StopReason.TIMED_OUT)
            return

        if not self.session.armed:
            self._refresh_status()
            return

        snapshot = self.monitor.snapshot()
        self.meter.set_level(snapshot.level_dbfs, snapshot.peak_dbfs)
        self.level_label.config(text=f"{snapshot.level_dbfs:7.1f} dBFS")

        if snapshot.error:
            self.error_label.config(
                text=f"❌ {snapshot.error}\n'마이크 변경'에서 다른 장치를 골라보세요.",
                foreground=w.ERROR)
            return
        self.error_label.config(text="")

        self._update_log(snapshot)

        # 박수를 감지했으면 할 일을 마쳤으므로 곧바로 대기 상태로 돌아간다
        if snapshot.trigger_count > 0:
            self.stop_listening(StopReason.TRIGGERED)
            return

        self._refresh_status()

    def _refresh_status(self) -> None:
        if self.session.armed:
            remaining = format_remaining(self.session.remaining(time.monotonic()))
            suffix = f"  ·  {remaining} 남음" if remaining else "  ·  무제한"
            self.status_label.config(text=f"🎧 듣는 중{suffix}", foreground=w.OK)
            self.toggle_button.config(text="⏹ 듣기 중지")
            if self.session.stop_reason is not StopReason.TRIGGERED:
                self.reason_label.config(text="박수 두 번(짝짝)을 기다리는 중…",
                                         foreground=w.FG_MUTED)
        else:
            self.status_label.config(text="💤 대기 중 · 마이크를 사용하지 않습니다",
                                     foreground=w.FG_MUTED)
            self.toggle_button.config(text="🎧 듣기 시작")
            hint = STOP_MESSAGES.get(self.session.stop_reason, "")
            if self.settings.auto_arm_on_unlock:
                hint += "\n화면을 잠갔다 풀면 자동으로 다시 듣습니다."
            self.reason_label.config(
                text=hint,
                foreground=w.OK if self.session.stop_reason is StopReason.TRIGGERED
                else w.FG_MUTED,
            )

    def _update_log(self, snapshot) -> None:
        """새로 들어온 소리만 로그에 덧붙인다 (매번 전체를 다시 그리면 깜빡인다)."""
        new_events, dropped = take_new_events(
            snapshot.events, snapshot.event_count, self._shown_events)
        if dropped:
            self.log.insert(tk.END, f" … {dropped}개 생략됨")

        for event in new_events:
            if event.triggered:
                text = "🎉 짝짝! 발동"
            elif event.is_clap:
                text = f"👏 박수 1회  {event.features.describe()}"
            else:
                text = f"·  {event.reject_reason}"
            self.log.insert(tk.END, f" {text}")
            self.log.see(tk.END)
        self._shown_events = snapshot.event_count

        # 목록이 무한정 길어지지 않게 오래된 줄을 지운다
        while self.log.size() > 200:
            self.log.delete(0)
