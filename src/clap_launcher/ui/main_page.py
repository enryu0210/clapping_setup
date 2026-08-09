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

import threading
import time
import tkinter as tk
from tkinter import ttk

from .. import autostart
from ..config import ConfigError, DetectionConfig, load_config
from ..launcher.app_launcher import AppLauncher
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
                 on_change_device, on_calibrate, on_edit_apps=None) -> None:
        super().__init__(parent, padding=(theme.px(24), theme.px(18)))
        self.monitor = monitor
        self.settings = settings
        self.on_change_device = on_change_device
        self.on_calibrate = on_calibrate
        self.on_edit_apps = on_edit_apps

        self.session = ListeningSession()
        self._shown_events = 0    # 로그에 이미 그린 이벤트의 누적 개수
        self._launcher = AppLauncher()
        self._launching = False   # 실행 중에 또 실행하지 않기 위한 표시

        self._build()
        # 설정 파일 문제는 **박수를 치기 전에** 알려줘야 한다.
        # 박수를 친 순간에야 "설정 파일이 없다"고 하면 가장 김이 새는 순간에 김이 샌다.
        self._show_launch_targets()
        # 프로그램을 방금 켰다는 것은 쓰겠다는 뜻이므로 바로 듣기 시작한다
        self.start_listening()

    # ── 화면 구성 ──────────────────────────────────────────
    def _build(self) -> None:
        self._build_header()

        self.status_label = IconLabel(self, width=520, icon="headphones", text="",
                                      color=theme.OK, font=theme.FONT_HEADING, icon_size=20)
        self.status_label.pack(anchor="w", pady=(theme.px(8), 0))

        self.reason_label = ttk.Label(self, text="", style="Muted.TLabel",
                                      wraplength=theme.px(520), justify="left")
        self.reason_label.pack(anchor="w", pady=(theme.px(2), theme.px(2)))
        self.device_label = ttk.Label(self, text=self._device_text(), style="Small.TLabel")
        self.device_label.pack(anchor="w", pady=(theme.px(2), theme.px(6)))

        # ── 음량 미터 ──
        meter_row = ttk.Frame(self)
        meter_row.pack(fill="x")
        self.meter = LevelMeter(meter_row)
        self.meter.pack(side="left")
        self.level_label = ttk.Label(meter_row, text="  --.- dBFS", style="Mono.TLabel")
        self.level_label.pack(side="left", padx=(theme.px(6), 0))

        self._build_log()
        self._build_options()
        self._build_buttons()

    def _build_header(self) -> None:
        # 캔버스에 직접 찍는 좌표라 전부 실제 픽셀로 바꿔서 쓴다
        size = theme.px(30)
        header = tk.Canvas(self, width=theme.px(520), height=theme.px(40), bg=theme.BG,
                           highlightthickness=0, bd=0)
        header.pack(anchor="w")
        icons.draw(header, "clap", size / 2 + theme.px(2), theme.px(20), size,
                   theme.ACCENT, width=2)
        header.create_text(theme.px(42), theme.px(21), text="Clapping Setup", anchor="w",
                           fill=theme.FG, font=theme.FONT_TITLE)

    def _build_log(self) -> None:
        ttk.Label(self, text="들린 소리 (걸러진 것 포함)", style="Small.TLabel").pack(
            anchor="w", pady=(theme.px(10), theme.px(4)))

        panel = NeoPanel(self, width=520, height=128, padding=10)
        panel.pack(anchor="w")
        self.log = tk.Listbox(
            panel.body, activestyle="none", bg=theme.BG_SUNKEN, fg=theme.FG_MUTED,
            highlightthickness=0, bd=0, font=theme.FONT_MONO,
            selectbackground=theme.BG_SUNKEN, selectforeground=theme.FG,
        )
        self.log.pack(fill="both", expand=True)

        self.error_label = ttk.Label(self, text="", style="Muted.TLabel",
                                     wraplength=theme.px(520))
        self.error_label.pack(anchor="w")

    def _build_options(self) -> None:
        """언제 들을지에 대한 설정들."""
        self.auto_arm_toggle = NeoToggleRow(
            self, text="화면 잠금을 풀면 자동으로 듣기 시작",
            value=self.settings.auto_arm_on_unlock, command=self._save_options,
        )
        self.auto_arm_toggle.pack(anchor="w", pady=(theme.px(6), 0))

        # ⚠️ 이 토글의 진짜 상태는 settings.json 이 아니라 Windows 레지스트리다.
        #    (사용자가 작업 관리자에서 직접 끌 수도 있어서) 화면을 열 때마다 실제 값을 읽는다.
        self.autostart_toggle = NeoToggleRow(
            self, text="Windows 시작할 때 자동 실행 (트레이에서 조용히 시작)",
            value=autostart.is_enabled(), command=self._save_autostart,
        )
        self.autostart_toggle.pack(anchor="w")

        row = ttk.Frame(self)
        row.pack(anchor="w", pady=(theme.px(2), theme.px(4)))
        ttk.Label(row, text="듣는 시간", style="Small.TLabel").pack(
            side="left", padx=(theme.px(2), theme.px(8)))
        self.timeout_picker = NeoSegmented(
            row, options=TIMEOUT_OPTIONS, value=self.settings.listen_timeout_min,
            command=self._save_options,
        )
        self.timeout_picker.pack(side="left")

    def _build_buttons(self) -> None:
        """버튼을 두 줄로 나눈 이유: 네 개를 한 줄에 두면 창 너비를 넘어 잘린다.
        자주 쓰는 것(듣기·프로그램 설정)을 윗줄에 둔다."""
        top = ttk.Frame(self)
        top.pack(anchor="w", pady=(theme.px(4), 0))
        self.toggle_button = NeoButton(top, text="듣기 중지", icon="stop",
                                       command=self._toggle_listening, accent=True)
        self.toggle_button.pack(side="left")
        NeoButton(top, text="프로그램 설정", icon="list",
                  command=self._open_apps_page).pack(side="left")

        bottom = ttk.Frame(self)
        bottom.pack(anchor="w")
        NeoButton(bottom, text="박수 보정", icon="target",
                  command=self.on_calibrate).pack(side="left")
        NeoButton(bottom, text="마이크 변경", icon="mic",
                  command=self.on_change_device).pack(side="left")

        # 박수를 쳤을 때 무엇이 실행되는지 / 실행 결과가 어땠는지를 보여주는 자리.
        # 마이크 오류(error_label)와 섞으면 한쪽이 다른 쪽을 지워버려서 따로 뒀다.
        self.launch_label = ttk.Label(self, text="", style="Small.TLabel",
                                      wraplength=theme.px(520), justify="left")
        self.launch_label.pack(anchor="w", pady=(theme.px(8), 0))

    def _open_apps_page(self) -> None:
        """프로그램 목록 편집 화면으로 넘어간다. 마이크는 잡고 있을 이유가 없으니 놓는다."""
        if self.on_edit_apps is None:
            return
        if self.session.armed:
            self.stop_listening(StopReason.MANUAL)
        self.on_edit_apps()

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

    def _save_autostart(self) -> None:
        """자동 실행 등록/해제. 실패하면 토글을 원래대로 되돌린다.

        되돌리는 이유: 켜진 것처럼 보이는데 실제로는 등록이 안 된 상태가 제일 나쁘다.
        다음 로그인 때 안 켜지고, 사용자는 이유를 알 수 없다.
        """
        wanted = self.autostart_toggle.value
        if autostart.set_enabled(wanted):
            return

        self.autostart_toggle.set(not wanted)
        self.launch_label.config(
            text="⚠ 자동 실행 설정을 바꾸지 못했습니다 (레지스트리에 쓸 수 없음).",
            foreground=theme.ERROR)

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

        # 박수를 감지했으면 할 일을 마쳤으므로 곧바로 대기 상태로 돌아간다.
        # ⚠️ 마이크를 먼저 놓고 나서 프로그램을 실행한다. 순서를 바꾸면 실행이 끝날 때까지
        #    마이크를 잡고 있게 되고, 그동안 들어온 소리로 또 발동할 여지가 생긴다.
        if snapshot.trigger_count > 0:
            self.stop_listening(StopReason.TRIGGERED)
            self.launch_apps()
            return

        self._refresh_status()

    # ── 프로그램 실행 ──────────────────────────────────────
    def _load_apps(self):
        """설정 파일에서 실행 목록을 읽는다. 실패하면 (None, 안내문)을 돌려준다.

        박수를 칠 때마다 다시 읽는 이유: apps.yaml 을 고친 뒤 프로그램을 껐다 켜야 한다면
        설정을 손보는 과정이 너무 번거롭다. 파일 읽기는 순식간이라 부담도 없다.
        """
        try:
            return load_config().enabled_apps, ""
        except ConfigError as exc:
            return None, str(exc)

    def _show_launch_targets(self) -> None:
        """지금 설정대로면 무엇이 실행되는지 미리 보여준다."""
        apps, error = self._load_apps()
        if apps is None:
            self.launch_label.config(text=f"⚠ {error}", foreground=theme.ERROR)
        elif not apps:
            self.launch_label.config(
                text="실행할 프로그램이 없습니다. config/apps.yaml 의 apps 목록을 채워주세요.",
                foreground=theme.FG_MUTED)
        else:
            names = ", ".join(app.name for app in apps)
            self.launch_label.config(text=f"박수 치면 실행: {names}", foreground=theme.FG_MUTED)

    def launch_apps(self) -> None:
        """등록된 프로그램들을 실행한다 (박수 감지 성공 시 호출)."""
        if self._launching:
            return                      # 이미 실행 중이면 무시 (중복 실행 방지)

        apps, error = self._load_apps()
        if apps is None:
            self.launch_label.config(text=f"⚠ {error}", foreground=theme.ERROR)
            return
        if not apps:
            self.launch_label.config(
                text="박수는 감지했지만 실행할 프로그램이 없습니다. config/apps.yaml 을 확인하세요.",
                foreground=theme.WARN)
            return

        self._launching = True
        self.launch_label.config(text=f"{len(apps)}개 실행 중…", foreground=theme.FG_MUTED)

        # ⚠️ 별도 스레드에서 도는 이유: delay 옵션 때문에 항목 사이에 몇 초씩 쉬어간다.
        #    화면 스레드에서 그대로 기다리면 그동안 창이 얼어붙어 고장 난 것처럼 보인다.
        threading.Thread(target=self._run_launch, args=(apps,),
                         daemon=True, name="app-launcher").start()

    def _run_launch(self, apps) -> None:
        """실행 스레드 본체. 여기서는 절대 위젯을 건드리지 않는다."""
        try:
            result = self._launcher.launch_all(apps)
        finally:
            self._launching = False

        # 위젯 갱신은 반드시 화면 스레드에서. after 로 넘겨준다.
        try:
            self.after(0, lambda: self._show_launch_result(result))
        except (tk.TclError, RuntimeError):
            pass       # 실행하는 사이에 창이 닫혔다 — 알릴 곳이 없으니 조용히 끝낸다

    def _show_launch_result(self, result) -> None:
        color = theme.OK if result.ok else theme.WARN
        self.launch_label.config(text=result.summary(), foreground=color)

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

    def set(self, value: bool) -> None:
        """밖에서 값을 바꾼다 (설정 저장에 실패해 되돌려야 할 때)."""
        self._toggle.set(value)
