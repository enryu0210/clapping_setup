"""보정 화면 — 사용자의 실제 소리로 감지 기준을 다시 잡는다.

2단계로 진행한다.

  1단계: 박수 5번        → "이건 박수다"
  2단계: 평소 소리 10초  → "이건 박수가 아니다" (타이핑·마우스 클릭 등)

⚠️ 2단계가 없으면 안 되는 이유 (실제로 겪은 실패):
1단계만으로 기준을 잡으면 "내 박수가 들어오게" 범위를 넓히기만 한다.
마이크가 고음을 덜 잡는 경우 그 범위가 너무 넓어져서, 넓어진 틈으로
**키보드 소리가 통째로 들어왔다.** 무엇을 배제할지 알려준 적이 없으니 당연한 결과다.
2단계에서 받은 잡음이 경계선을 반대쪽에서 눌러줘야 제대로 갈린다.
"""

import time
import tkinter as tk
from tkinter import ttk

from ..config import DetectionConfig
from ..detector.calibration import (
    MIN_SAMPLE_PEAK,
    NOISE_COLLECT_SEC,
    REQUIRED_SAMPLES,
    derive_config,
)
from ..settings import save_settings
from . import icons, theme
from .audio_monitor import AudioMonitor, take_new_events
from .neumorphic import IconLabel, NeoButton, NeoPanel

PHASE_CLAP = "clap"      # 박수 모으는 중
PHASE_NOISE = "noise"    # 잡음 모으는 중
PHASE_DONE = "done"      # 계산 끝

PANEL_WIDTH = 520


class CalibratePage(ttk.Frame):
    """박수와 잡음을 받아 기준값을 계산하는 화면."""

    def __init__(self, parent, monitor: AudioMonitor, settings, on_done) -> None:
        super().__init__(parent, padding=(theme.px(24), theme.px(18)))
        self.monitor = monitor
        self.settings = settings
        self.on_done = on_done

        self.phase = PHASE_CLAP
        self.samples = []          # 박수 특징값
        self.noise = []            # 잡음 특징값
        self._consumed = 0         # 지금까지 읽어간 이벤트의 누적 개수
        self._ignored = 0          # 너무 작아서 무시한 소리 개수
        self._noise_started_at = 0.0
        self.result = None

        self._build()
        self.restart()

    # ── 화면 구성 ──────────────────────────────────────────
    def _build(self) -> None:
        header = tk.Canvas(self, width=theme.px(PANEL_WIDTH), height=theme.px(40), bg=theme.BG,
                           highlightthickness=0, bd=0)
        header.pack(anchor="w")
        icons.draw(header, "target", theme.px(16), theme.px(20), theme.px(26), theme.ACCENT, width=2)
        header.create_text(theme.px(38), theme.px(21), text="박수 보정", anchor="w",
                           fill=theme.FG, font=theme.FONT_TITLE)

        self.instruction = ttk.Label(self, text="", style="Muted.TLabel",
                                     justify="left", wraplength=theme.px(PANEL_WIDTH))
        self.instruction.pack(anchor="w", pady=(theme.px(6), theme.px(10)))

        self.progress_label = IconLabel(self, width=PANEL_WIDTH, icon="clap", text="",
                                        color=theme.FG_MUTED, font=theme.FONT_HEADING,
                                        icon_size=20)
        self.progress_label.pack(anchor="w")
        self.hint_label = ttk.Label(self, text="", style="Small.TLabel",
                                    wraplength=theme.px(PANEL_WIDTH))
        self.hint_label.pack(anchor="w", pady=(theme.px(2), theme.px(8)))

        # 모은 샘플의 값을 그대로 보여준다.
        # 사용자가 "기침이 잘못 들어갔네" 같은 걸 알아챌 수 있어야 하기 때문이다.
        self.list_caption = ttk.Label(self, text="모은 박수", style="Small.TLabel")
        self.list_caption.pack(anchor="w", pady=(0, theme.px(4)))

        panel = NeoPanel(self, width=PANEL_WIDTH, height=130, padding=10)
        panel.pack(anchor="w")
        self.sample_list = tk.Listbox(
            panel.body, activestyle="none", bg=theme.BG_SUNKEN, fg=theme.FG,
            highlightthickness=0, bd=0, font=theme.FONT_MONO,
            selectbackground=theme.BG_SUNKEN, selectforeground=theme.FG,
        )
        self.sample_list.pack(fill="both", expand=True)

        self.result_label = ttk.Label(self, text="", style="Muted.TLabel",
                                      wraplength=theme.px(PANEL_WIDTH), justify="left")
        self.result_label.pack(anchor="w", pady=(theme.px(10), theme.px(6)))

        row = ttk.Frame(self)
        row.pack(anchor="w")
        self.primary_button = NeoButton(row, text="저장하고 적용", icon="check",
                                        command=self._save, accent=True)
        self.primary_button.pack(side="left")
        self.undo_button = NeoButton(row, text="마지막 지우기", icon="undo",
                                     command=self._undo)
        self.undo_button.pack(side="left")
        NeoButton(row, text="다시 하기", icon="refresh",
                  command=self.restart).pack(side="left")
        NeoButton(row, text="취소", icon="close", command=self._cancel).pack(side="left")

    # ── 단계 진행 ─────────────────────────────────────────
    def restart(self) -> None:
        """처음부터 다시 모은다."""
        self.phase = PHASE_CLAP
        self.samples.clear()
        self.noise.clear()
        self.sample_list.delete(0, tk.END)
        self._ignored = 0
        self.result = None
        self.result_label.config(text="")
        self.primary_button.configure_state(False)
        self.primary_button.set_text("저장하고 적용", "check")
        self.undo_button.configure_state(True)
        self.list_caption.config(text="모은 박수")
        self.instruction.config(
            text="1단계 — 이 마이크로 친 진짜 박수를 기준으로 삼습니다.\n"
                 "평소 치던 대로, 0.5초 이상 간격을 두고 천천히 쳐주세요.",
            foreground=theme.FG_MUTED,
        )
        self._start_listening()
        self._refresh_progress()

    def _start_listening(self) -> None:
        """느슨한 조건으로 감지기를 돌린다 (보정 중에는 거의 다 받아서 관찰해야 한다)."""
        self.monitor.start(self.settings.device, DetectionConfig.for_calibration())
        self._consumed = 0

    def _begin_noise_phase(self) -> None:
        """2단계: 배제해야 할 소리를 모은다."""
        self.phase = PHASE_NOISE
        self._noise_started_at = time.monotonic()
        self.list_caption.config(text="모은 잡음 (배제할 소리)")
        self.sample_list.delete(0, tk.END)
        self.undo_button.configure_state(False)
        self.primary_button.configure_state(True)
        self.primary_button.set_text("건너뛰고 마치기", "play")
        self.instruction.config(
            text="2단계 — 이번엔 '박수가 아닌 소리'를 알려줄 차례입니다.\n"
                 "평소처럼 타이핑하거나, 마우스를 클릭하거나, 책상을 두드려 주세요.\n"
                 "여기서 모은 소리는 앞으로 무시하도록 기준을 잡습니다.",
            foreground=theme.ACCENT,
        )
        self._refresh_progress()

    def _cancel(self) -> None:
        self.on_done()

    def _undo(self) -> None:
        """마지막 박수 샘플 하나를 지운다. 기침 같은 게 잘못 들어갔을 때 쓴다."""
        if self.phase != PHASE_CLAP or not self.samples:
            return
        self.samples.pop()
        self.sample_list.delete(tk.END)
        self._refresh_progress()

    # ── 수집 ──────────────────────────────────────────────
    def update_from_monitor(self) -> None:
        """창이 주기적으로 불러준다. 새로 들어온 소리를 단계에 맞게 담는다."""
        snapshot = self.monitor.snapshot()

        if snapshot.error:
            self.hint_label.config(text=snapshot.error, foreground=theme.ERROR)
            return

        if self.phase == PHASE_DONE:
            return

        # 누적 개수로 세야 한다. 목록 길이로 세면 버퍼가 찬 뒤로 멈춰버린다.
        new_events, _dropped = take_new_events(
            snapshot.events, snapshot.event_count, self._consumed
        )
        self._consumed = snapshot.event_count

        if self.phase == PHASE_CLAP:
            self._collect_claps(new_events)
        else:
            self._collect_noise(new_events)

    def _collect_claps(self, new_events) -> None:
        for event in new_events:
            if len(self.samples) >= REQUIRED_SAMPLES:
                break
            # 작은 소리는 무시한다. 보정 중에 들어오는 작은 소리는 대부분
            # 사용자가 의도한 박수가 아니라 주변 소음이다(에어컨, 의자, 옷깃).
            if event.features.peak < MIN_SAMPLE_PEAK:
                self._ignored += 1
                continue
            self.samples.append(event.features)
            self.sample_list.insert(tk.END, f" {len(self.samples)}. {event.features.describe()}")
            self.sample_list.see(tk.END)

        self._refresh_progress()
        if len(self.samples) >= REQUIRED_SAMPLES:
            self._begin_noise_phase()

    def _collect_noise(self, new_events) -> None:
        for event in new_events:
            # 잡음은 작아도 받는다. 실제로 타이핑은 박수보다 작기 때문이다.
            self.noise.append(event.features)
            self.sample_list.insert(tk.END, f" {len(self.noise)}. {event.features.describe()}")
            self.sample_list.see(tk.END)

        remaining = NOISE_COLLECT_SEC - (time.monotonic() - self._noise_started_at)
        if remaining <= 0:
            self._finish()
        else:
            self._refresh_progress(remaining)

    def _refresh_progress(self, remaining: float = 0.0) -> None:
        if self.phase == PHASE_CLAP:
            done = len(self.samples)
            dots = "●" * done + "○" * max(0, REQUIRED_SAMPLES - done)
            self.progress_label.set(f"{dots}   박수 {done} / {REQUIRED_SAMPLES}",
                                    "clap", theme.OK if done else theme.FG_MUTED)
            extra = f"  (작아서 무시한 소리 {self._ignored}개)" if self._ignored else ""
            self.hint_label.config(text=f"박수를 쳐주세요…{extra}", foreground=theme.FG_MUTED)
        elif self.phase == PHASE_NOISE:
            self.progress_label.set(
                f"{remaining:.0f}초 남음   ·   모은 소리 {len(self.noise)}개",
                "clock", theme.ACCENT)
            self.hint_label.config(text="타이핑·클릭 등 평소 나는 소리를 내주세요…",
                                   foreground=theme.FG_MUTED)

    # ── 마무리 ────────────────────────────────────────────
    def _finish(self) -> None:
        """다 모았다. 기준값을 계산해서 보여준다."""
        self.phase = PHASE_DONE
        self.monitor.stop()      # 더 받을 필요가 없으니 마이크를 놓아준다
        self.hint_label.config(text="")
        self.instruction.config(text="아래 기준값이 이 마이크에 맞춰 계산됐습니다.",
                                foreground=theme.FG_MUTED)

        try:
            self.result = derive_config(self.samples, self.noise)
        except ValueError as exc:
            self.progress_label.set("보정 실패", "warning", theme.ERROR)
            self.result_label.config(text=str(exc), foreground=theme.ERROR)
            return

        self.progress_label.set("보정 완료", "check", theme.OK)

        config = self.result.config
        lines = [
            f"박수 {self.result.sample_count}개 · 잡음 {self.result.noise_count}개로 계산:",
            f"  · 고음 비율   {config.min_high_freq_ratio:.2f} 이상",
            f"  · 잡음스러움  {config.min_flatness:.2f} ~ {config.max_flatness:.2f}",
            f"  · 날카로움    {config.min_zero_crossing_rate:.2f} 이상",
            f"  · 음정        {config.max_harmonicity:.2f} 이하   (기침·말소리 배제)",
            f"  · 소리 길이   {config.min_decay_ms:.0f} ~ {config.max_decay_ms:.0f}ms"
            f"   (짧으면 키보드, 길면 종이)",
        ]
        if self.result.noise_count:
            blocked = self.result.rejected_noise
            total = self.result.noise_count
            lines.append(f"\n모은 잡음 {total}개 중 {blocked}개를 막아냅니다.")
        for warning in self.result.warnings:
            lines.append(f"\n· {warning}")

        self.result_label.config(
            text="\n".join(lines),
            foreground=theme.WARN if self.result.warnings else theme.FG_MUTED,
        )
        self.primary_button.set_text("저장하고 적용", "check")
        self.primary_button.configure_state(True)

    def _save(self) -> None:
        """2단계 중이면 건너뛰고 마무리, 끝났으면 저장하고 돌아간다."""
        if self.phase == PHASE_NOISE:
            self._finish()
            return
        if self.result is None:
            return

        self.settings.detection = self.result.config.to_dict()
        try:
            save_settings(self.settings)
        except OSError as exc:
            # 저장에 실패해도 이번 실행에는 적용된다. 다음 실행 때 다시 보정하면 된다.
            self.result_label.config(
                text=f"저장하지 못했습니다({exc}). 이번 실행에만 적용됩니다.",
                foreground=theme.WARN,
            )
        self.on_done()
