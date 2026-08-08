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
from . import icons, theme
from .audio_monitor import AudioMonitor, take_new_events
from .neumorphic import IconLabel, NeoButton, NeoPanel, NeoSegmented
from .widgets import METER_MIN_DBFS, LevelMeter

TIMEOUT_OPTIONS = [("1분", 1.0), ("3분", 3.0), ("5분", 5.0), ("10분", 10.0), ("무제한", 0.0)]

# 멈춘 이유별 안내 문구와 아이콘
STOP_MESSAGES = {
    StopReason.NEVER_STARTED: ("듣기를 시작하면 박수를 기다립니다.", "standby"),
    StopReason.TRIGGERED: ("박수를 감지해서 실행했습니다.", "sparkle"),
    StopReason.TIMED_OUT: ("정해진 시간 동안 박수가 없어 멈췄습니다.", "clock"),
    StopReason.MANUAL: ("직접 멈췄습니다.", "standby"),
}


class MainPage(ttk.Frame):
    """듣기 상태 관리 + 감지 로그 화면."""

    def __init__(self, parent, monitor: AudioMonitor, settings,
                 on_change_device, on_calibrate) -> None:
        super().__init__(parent, padding=(24, 20))
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
        self._build_header()

        self.status_label = IconLabel(self, width=520, icon="headphones", text="",
                                      color=theme.OK, font=theme.FONT_HEADING, icon_size=20)
        self.status_label.pack(anchor="w", pady=(10, 0))

        self.reason_label = ttk.Label(self, text="", style="Muted.TLabel", wraplength=520,
                                      justify="left")
        self.reason_label.pack(anchor="w", pady=(2, 2))
        self.device_label = ttk.Label(self, text=self._device_text(), style="Small.TLabel")
        self.device_label.pack(anchor="w", pady=(2, 6))

        # ── 음량 미터 ──
        meter_row = ttk.Frame(self)
        meter_row.pack(fill="x")
        self.meter = LevelMeter(meter_row)
        self.meter.pack(side="left")
        self.level_label = ttk.Label(meter_row, text="  --.- dBFS", style="Mono.TLabel")
        self.level_label.pack(side="left", padx=(6, 0))

        self._build_log()
        self._build_options()
        self._build_buttons()

    def _build_header(self) -> None:
        header = tk.Canvas(self, width=520, height=38, bg=theme.BG,
                           highlightthickness=0, bd=0)
        header.pack(anchor="w")
        icons.draw(header, "clap", 16, 19, 28, theme.ACCENT, width=2)
        header.create_text(40, 20, text="Clapping Setup", anchor="w",
                           fill=theme.FG, font=theme.FONT_TITLE)

    def _build_log(self) -> None:
        ttk.Label(self, text="들린 소리 (걸러진 것 포함)", style="Small.TLabel").pack(
            anchor="w", pady=(12, 4))

        panel = NeoPanel(self, width=520, height=150, padding=10)
        panel.pack(anchor="w")
        self.log = tk.Listbox(
            panel.body, activestyle="none", bg=theme.BG_SUNKEN, fg=theme.FG_MUTED,
            highlightthickness=0, bd=0, font=theme.FONT_MONO,
            selectbackground=theme.BG_SUNKEN, selectforeground=theme.FG,
        )
        self.log.pack(fill="both", expand=True)

        self.error_label = ttk.Label(self, text="", style="Muted.TLabel", wraplength=520)
        self.error_label.pack(anchor="w")

    def _build_options(self) -> None:
        """언제 들을지에 대한 설정 두 가지."""
        self.auto_arm_toggle = NeoToggleRow(
            self, text="화면 잠금을 풀면 자동으로 듣기 시작",
            value=self.settings.auto_arm_on_unlock, command=self._save_options,
        )
        self.auto_arm_toggle.pack(anchor="w", pady=(8, 0))

        row = ttk.Frame(self)
        row.pack(anchor="w", pady=(2, 6))
        ttk.Label(row, text="듣는 시간", style="Small.TLabel").pack(side="left", padx=(2, 8))
        self.timeout_picker = NeoSegmented(
            row, options=TIMEOUT_OPTIONS, value=self.settings.listen_timeout_min,
            command=self._save_options,
        )
        self.timeout_picker.pack(side="left")

    def _build_buttons(self) -> None:
        row = ttk.Frame(self)
        row.pack(anchor="w", pady=(4, 0))
        self.toggle_button = NeoButton(row, text="듣기 중지", icon="stop",
                                       command=self._toggle_listening, accent=True)
        self.toggle_button.pack(side="left")
        NeoButton(row, text="박수 보정", icon="target",
                  command=self.on_calibrate).pack(side="left")
        NeoButton(row, text="마이크 변경", icon="mic",
                  command=self.on_change_device).pack(side="left")

    def _device_text(self) -> str:
        mic = self.settings.device_label or "기본 장치"
        tuned = "보정됨" if self.settings.detection else "기본 기준값"
        return f"마이크: {mic}  ·  {tuned}"

    def _save_options(self) -> None:
        """설정을 바꾸면 바로 저장한다. 다음 실행에도 유지되어야 하기 때문이다."""
        self.settings.auto_arm_on_unlock = self.auto_arm_toggle.value
        self.settings.listen_timeout_min = self.timeout_picker.value
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
        self.meter.set_level(METER_MIN_DBFS, METER_MIN_DBFS)
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
        self.reason_label.config(text="화면 잠금이 풀려서 듣기를 시작했습니다.",
                                 foreground=theme.ACCENT)

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
                text=f"{snapshot.error}\n'마이크 변경'에서 다른 장치를 골라보세요.",
                foreground=theme.ERROR)
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
            self.status_label.set(f"듣는 중{suffix}", "headphones", theme.OK)
            self.toggle_button.set_text("듣기 중지", "stop")
            if self.session.stop_reason is not StopReason.TRIGGERED:
                self.reason_label.config(text="박수 두 번(짝짝)을 기다리는 중…",
                                         foreground=theme.FG_MUTED)
        else:
            self.status_label.set("대기 중 · 마이크를 사용하지 않습니다",
                                  "standby", theme.FG_MUTED)
            self.toggle_button.set_text("듣기 시작", "play")
            message, _icon = STOP_MESSAGES.get(self.session.stop_reason, ("", "standby"))
            if self.settings.auto_arm_on_unlock:
                message += "\n화면을 잠갔다 풀면 자동으로 다시 듣습니다."
            self.reason_label.config(
                text=message,
                foreground=theme.OK if self.session.stop_reason is StopReason.TRIGGERED
                else theme.FG_MUTED,
            )

    def _update_log(self, snapshot) -> None:
        """새로 들어온 소리만 로그에 덧붙인다 (매번 전체를 다시 그리면 깜빡인다)."""
        new_events, dropped = take_new_events(
            snapshot.events, snapshot.event_count, self._shown_events)
        if dropped:
            self.log.insert(tk.END, f"  … {dropped}개 생략됨")

        for event in new_events:
            if event.triggered:
                text = "짝짝! 발동"
            elif event.is_clap:
                text = f"박수 1회  {event.features.describe()}"
            else:
                text = f"·  {event.reject_reason}"
            self.log.insert(tk.END, f"  {text}")
            self.log.see(tk.END)
        self._shown_events = snapshot.event_count

        # 목록이 무한정 길어지지 않게 오래된 줄을 지운다
        while self.log.size() > 200:
            self.log.delete(0)


class NeoToggleRow(ttk.Frame):
    """토글 스위치를 다른 위젯처럼 pack 할 수 있게 감싼 것."""

    def __init__(self, parent, text: str, value: bool, command=None) -> None:
        super().__init__(parent)
        from .neumorphic import NeoToggle

        self._toggle = NeoToggle(self, text=text, value=value, command=command)
        self._toggle.pack(side="left")

    @property
    def value(self) -> bool:
        return self._toggle.value
