"""음량 막대 위젯과 그 계산.

색·글꼴은 theme.py, 입체 표면은 neumorphic.py 가 담당한다.
여기 남은 것은 **음량 값을 막대로 바꾸는 계산**과 그것을 그리는 위젯뿐이다.

계산 부분(dbfs_to_ratio, segment_color)을 그리기와 분리해 둔 이유:
창을 띄우지 않고 테스트할 수 있어야 하기 때문이다. 막대가 범위를 벗어나면
IndexError로 프로그램이 죽는데, 그건 눈으로 확인하기 어렵다.
"""

import tkinter as tk

from . import theme
from .neumorphic import _make_surface

# ── 화면 밖에서도 쓰는 값 ─────────────────────────────────
METER_MIN_DBFS = -60.0   # 이보다 조용하면 막대가 빈다 (조용한 방 수준)
METER_SEGMENTS = 28      # 막대 칸 수

# 이전 코드와의 호환을 위해 테마 색을 이 이름으로도 노출한다
BG = theme.BG
BG_PANEL = theme.BG_SUNKEN
FG = theme.FG
FG_MUTED = theme.FG_MUTED
ACCENT = theme.ACCENT
OK = theme.OK
WARN = theme.WARN
ERROR = theme.ERROR
METER_OFF = theme.METER_OFF
FONT_TITLE = theme.FONT_TITLE
FONT_BODY = theme.FONT_BODY
FONT_SMALL = theme.FONT_SMALL
FONT_MONO = theme.FONT_MONO


def dbfs_to_ratio(dbfs: float, min_dbfs: float = METER_MIN_DBFS) -> float:
    """dBFS 값을 막대 채움 비율(0.0~1.0)로 바꾼다.

    화면 그리기와 분리된 순수 계산 함수라 테스트하기 쉽다.
    범위를 벗어난 값(클리핑으로 0dB 초과 등)이 들어와도 0~1 밖으로 나가지 않게 자른다.
    """
    if dbfs <= min_dbfs:
        return 0.0
    ratio = (dbfs - min_dbfs) / (0.0 - min_dbfs)
    return min(1.0, max(0.0, ratio))


def segment_color(index: int, total: int) -> str:
    """막대 칸의 색. 오른쪽으로 갈수록 초록 → 노랑 → 빨강.

    소리가 너무 커서 찌그러지는(클리핑) 구간을 눈으로 알 수 있게 하기 위함이다.
    """
    position = index / max(1, total - 1)
    if position < 0.65:
        return theme.METER_LOW
    if position < 0.85:
        return theme.METER_MID
    return theme.METER_HIGH


class LevelMeter(tk.Canvas):
    """음량을 칸 막대로 보여주는 위젯.

    뉴모피즘답게 **움푹 파인 홈 안에 칸이 켜지는** 모양으로 그린다.
    성능을 위해 칸(사각형)을 처음에 한 번만 만들고, 그다음부터는 색만 바꾼다.
    매번 지우고 다시 그리면 화면이 깜빡인다.
    """

    def __init__(self, parent, width: int = 340, height: int = 26, **kwargs) -> None:
        from .neumorphic import theme as _t   # 그림자 여백 계산에 필요한 값

        self.pad = _t.SHADOW_BLUR * 2 + _t.SHADOW_OFFSET
        super().__init__(
            parent, width=width + self.pad * 2, height=height + self.pad * 2,
            bg=theme.BG, highlightthickness=0, bd=0, **kwargs,
        )
        self.track_width = width
        self.track_height = height

        # 홈(움푹 들어간 바닥)
        self._track_image = _make_surface(width, height, height // 2, False,
                                          theme.BG_SUNKEN, theme.SHADOW_OFFSET - 1,
                                          theme.SHADOW_BLUR - 2)
        if self._track_image is not None:
            self.create_image(0, 0, image=self._track_image, anchor="nw")

        self._segments: list[int] = []
        self._build_segments()

    def _build_segments(self) -> None:
        inner_pad = 6                      # 홈 안쪽 여백 (칸이 홈 벽에 닿지 않게)
        usable = self.track_width - inner_pad * 2
        gap = 2
        seg_width = (usable - gap * (METER_SEGMENTS - 1)) / METER_SEGMENTS
        top = self.pad + inner_pad * 0.7
        bottom = self.pad + self.track_height - inner_pad * 0.7

        for i in range(METER_SEGMENTS):
            x0 = self.pad + inner_pad + i * (seg_width + gap)
            self._segments.append(self.create_rectangle(
                x0, top, x0 + seg_width, bottom, fill=theme.METER_OFF, width=0,
            ))

    def set_level(self, dbfs: float, peak_dbfs: float) -> None:
        """현재 음량과 최고점을 반영해 칸 색을 갱신한다."""
        filled = round(dbfs_to_ratio(dbfs) * METER_SEGMENTS)
        peak_index = round(dbfs_to_ratio(peak_dbfs) * METER_SEGMENTS) - 1

        for i, rect in enumerate(self._segments):
            if i < filled:
                color = segment_color(i, METER_SEGMENTS)
            elif i == peak_index and peak_index >= 0:
                # 최고점 표시: 소리가 사라진 뒤에도 잠깐 남아서 '방금 얼마나 컸는지' 보여준다
                color = theme.FG_MUTED
            else:
                color = theme.METER_OFF
            self.itemconfig(rect, fill=color)
