"""보정 화면 — 사용자의 실제 박수로 감지 기준을 다시 잡는다.

이 화면이 리미터(클리핑 가드) 문제의 실질적인 해법이다.
기본 기준값은 '평균적인 박수' 기준이라, 소프트웨어 처리를 거친 마이크에서는
값이 조금씩 다르게 나온다. 그 마이크로 친 진짜 박수를 몇 번 받아서 기준을 다시 잡으면
그 환경에 맞는 값이 된다.

수집할 때는 판별 조건을 전부 열어둔다(DetectionConfig.permissive).
기본 기준으로 걸러버리면 정작 보정이 필요한 마이크에서 아무것도 못 모은다.
"""

import tkinter as tk
from tkinter import ttk

from ..config import DetectionConfig
from ..detector.calibration import MIN_SAMPLE_PEAK, REQUIRED_SAMPLES, derive_config
from ..settings import save_settings
from . import widgets as w
from .audio_monitor import AudioMonitor


class CalibratePage(ttk.Frame):
    """박수를 몇 번 받아 기준값을 계산하는 화면."""

    def __init__(self, parent, monitor: AudioMonitor, settings, on_done) -> None:
        super().__init__(parent, padding=20)
        self.monitor = monitor
        self.settings = settings
        self.on_done = on_done

        self.samples = []          # 모은 박수의 특징값
        self._consumed = 0         # 모니터의 이벤트 목록 중 어디까지 읽었는지
        self._ignored = 0          # 너무 작아서 무시한 소리 개수
        self.result = None         # 계산된 보정 결과

        self._build()
        self.start_collecting()

    # ── 화면 구성 ──────────────────────────────────────────
    def _build(self) -> None:
        ttk.Label(self, text="🎯 박수 보정", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="이 마이크로 친 진짜 박수를 기준으로 삼습니다.\n"
                 "평소 치던 대로, 0.5초 이상 간격을 두고 천천히 쳐주세요.",
            style="Muted.TLabel", justify="left",
        ).pack(anchor="w", pady=(4, 16))

        self.progress_label = ttk.Label(self, text="", style="Status.TLabel")
        self.progress_label.pack(anchor="w")
        self.hint_label = ttk.Label(self, text="", style="Small.TLabel", wraplength=500)
        self.hint_label.pack(anchor="w", pady=(2, 12))

        # 모은 샘플의 값을 그대로 보여준다.
        # 사용자가 "기침이 잘못 들어갔네" 같은 걸 알아챌 수 있어야 하기 때문이다.
        box = ttk.LabelFrame(self, text=" 모은 박수 ", padding=10)
        box.pack(fill="both", expand=True)
        self.sample_list = tk.Listbox(
            box, height=7, activestyle="none",
            bg=w.BG_PANEL, fg=w.FG, highlightthickness=0, bd=0, font=w.FONT_MONO,
            selectbackground=w.BG_PANEL, selectforeground=w.FG,
        )
        self.sample_list.pack(fill="both", expand=True)

        self.result_label = ttk.Label(self, text="", style="Muted.TLabel", wraplength=500,
                                      justify="left")
        self.result_label.pack(anchor="w", pady=(12, 8))

        row = ttk.Frame(self)
        row.pack(fill="x")
        self.save_button = ttk.Button(row, text="저장하고 적용", command=self._save,
                                      state="disabled", style="Accent.TButton")
        self.save_button.pack(side="left")
        # 잘못 들어간 샘플(기침 등)을 하나만 지울 수 있어야 처음부터 다시 안 해도 된다
        ttk.Button(row, text="↶ 마지막 지우기", command=self._undo).pack(side="left", padx=8)
        ttk.Button(row, text="다시 하기", command=self.start_collecting).pack(side="left")
        ttk.Button(row, text="취소", command=self.on_done).pack(side="left", padx=8)

    # ── 수집 ──────────────────────────────────────────────
    def start_collecting(self) -> None:
        """처음부터 다시 모은다."""
        self.samples.clear()
        self.sample_list.delete(0, tk.END)
        self._ignored = 0
        self.result = None
        self.result_label.config(text="")
        self.save_button.config(state="disabled")
        self._refresh_progress()

        # 느슨한 조건으로 감지기를 돌린다 (위 파일 설명 참고)
        self.monitor.start(self.settings.device, DetectionConfig.for_calibration())
        self._consumed = 0

    def _undo(self) -> None:
        """마지막 샘플 하나를 지운다. 기침 같은 게 잘못 들어갔을 때 쓴다."""
        if not self.samples:
            return
        self.samples.pop()
        self.sample_list.delete(tk.END)
        self.result = None
        self.result_label.config(text="")
        self.save_button.config(state="disabled")
        # 다 모아서 멈춰 있었다면 다시 듣기 시작한다
        if not self.monitor.snapshot().running:
            self.monitor.start(self.settings.device, DetectionConfig.for_calibration())
            self._consumed = 0
        self._refresh_progress()

    def update_from_monitor(self) -> None:
        """창이 주기적으로 불러준다. 새로 들어온 소리를 샘플로 담는다."""
        snapshot = self.monitor.snapshot()

        if snapshot.error:
            self.hint_label.config(text=f"❌ {snapshot.error}", foreground=w.ERROR)
            return

        if len(self.samples) >= REQUIRED_SAMPLES:
            return   # 다 모았으면 더 받지 않는다

        # 모니터는 최근 이벤트만 들고 있으므로, 아직 안 읽은 것만 가져온다
        new_events = snapshot.events[self._consumed:]
        self._consumed = len(snapshot.events)

        for event in new_events:
            if len(self.samples) >= REQUIRED_SAMPLES:
                break
            # 작은 소리는 무시한다. 보정 중에 들어오는 작은 소리는 대부분
            # 사용자가 의도한 박수가 아니라 주변 소음이다(에어컨, 의자, 옷깃).
            if event.features.peak < MIN_SAMPLE_PEAK:
                self._ignored += 1
                continue
            self.samples.append(event.features)
            self.sample_list.insert(
                tk.END, f" {len(self.samples)}. {event.features.describe()}"
            )
            self.sample_list.see(tk.END)

        self._refresh_progress()
        if len(self.samples) >= REQUIRED_SAMPLES:
            self._finish()

    def _refresh_progress(self) -> None:
        done = len(self.samples)
        dots = "●" * done + "○" * max(0, REQUIRED_SAMPLES - done)
        self.progress_label.config(text=f"{dots}  {done} / {REQUIRED_SAMPLES}",
                                   foreground=w.OK if done else w.FG_MUTED)
        if done < REQUIRED_SAMPLES:
            extra = f"  (작아서 무시한 소리 {self._ignored}개)" if self._ignored else ""
            self.hint_label.config(text=f"박수를 쳐주세요…{extra}", foreground=w.FG_MUTED)

    def _finish(self) -> None:
        """다 모았다. 기준값을 계산해서 보여준다."""
        self.monitor.stop()      # 더 받을 필요가 없으니 마이크를 놓아준다
        self.hint_label.config(text="다 모았습니다.", foreground=w.OK)

        try:
            self.result = derive_config(self.samples)
        except ValueError as exc:
            self.result_label.config(text=f"❌ {exc}", foreground=w.ERROR)
            return

        config = self.result.config
        lines = [
            "이 마이크에 맞춰 계산된 기준값:",
            f"  · 고음 비율   {config.min_high_freq_ratio:.2f} 이상",
            f"  · 잡음스러움  {config.min_flatness:.2f} ~ {config.max_flatness:.2f}",
            f"  · 날카로움    {config.min_zero_crossing_rate:.2f} 이상",
            f"  · 음정        {config.max_harmonicity:.2f} 이하  (기침·말소리 배제)",
            f"  · 소리 길이   {config.max_decay_ms:.0f}ms 이하  (종이·음악 배제)",
        ]
        for warning in self.result.warnings:
            lines.append(f"\n⚠️ {warning}")

        self.result_label.config(
            text="\n".join(lines),
            foreground=w.WARN if self.result.warnings else w.FG_MUTED,
        )
        self.save_button.config(state="normal")

    def _save(self) -> None:
        """계산한 기준값을 저장하고 돌아간다."""
        if self.result is None:
            return
        self.settings.detection = self.result.config.to_dict()
        try:
            save_settings(self.settings)
        except OSError as exc:
            # 저장에 실패해도 이번 실행에는 적용된다. 다음 실행 때 다시 보정하면 된다.
            self.result_label.config(
                text=f"⚠️ 저장하지 못했습니다({exc}). 이번 실행에만 적용됩니다.",
                foreground=w.WARN,
            )
        self.on_done()
