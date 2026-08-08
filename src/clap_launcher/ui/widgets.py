"""화면 여기저기서 재사용하는 조각들 — 색 팔레트와 음량 막대 위젯.

색과 글꼴을 여기 한 곳에 모아둔 이유: 나중에 테마를 바꿀 때 파일 하나만 고치면 된다.
화면 파일마다 색 코드를 직접 적어두면 색을 하나 바꿀 때 온 파일을 뒤져야 한다.
"""

import tkinter as tk

# ── 색 팔레트 ──────────────────────────────────────────────
BG = "#1e1f26"          # 창 배경 (어두운 회색)
BG_PANEL = "#2a2c36"    # 목록·미터 같은 패널 배경
FG = "#e8e8ec"          # 기본 글자색
FG_MUTED = "#9a9cab"    # 설명글처럼 덜 중요한 글자
ACCENT = "#5b8dff"      # 강조 (선택된 항목, 버튼)
OK = "#3ecf8e"          # 정상·성공
WARN = "#ffc857"        # 주의
ERROR = "#ff6b6b"       # 오류
METER_OFF = "#3a3d4a"   # 꺼진 막대 칸

FONT_TITLE = ("맑은 고딕", 15, "bold")
FONT_BODY = ("맑은 고딕", 10)
FONT_SMALL = ("맑은 고딕", 9)
FONT_MONO = ("Consolas", 10)

# ── 음량 막대 ──────────────────────────────────────────────
METER_MIN_DBFS = -60.0   # 이보다 조용하면 막대가 빈다 (조용한 방 수준)
METER_SEGMENTS = 28      # 막대 칸 수


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
        return OK
    if position < 0.85:
        return WARN
    return ERROR


class LevelMeter(tk.Canvas):
    """음량을 칸 막대로 보여주는 위젯.

    성능을 위해 칸(사각형)을 처음에 한 번만 만들고, 그다음부터는 색만 바꾼다.
    매번 지우고 다시 그리면 화면이 깜빡인다.
    """

    # 폭 기본값 근거: 창 안쪽 폭(약 520px)에서 옆에 붙는 'dBFS' 숫자 자리를 뺀 크기.
    # 이보다 키우면 숫자가 창 밖으로 밀려 잘린다.
    def __init__(self, parent, width: int = 375, height: int = 26, **kwargs) -> None:
        super().__init__(
            parent, width=width, height=height,
            bg=BG_PANEL, highlightthickness=0, bd=0, **kwargs,
        )
        self._segments: list[int] = []   # 캔버스 도형 ID 목록
        self._build(width, height)

    def _build(self, width: int, height: int) -> None:
        gap = 2
        seg_width = (width - gap * (METER_SEGMENTS - 1)) / METER_SEGMENTS
        for i in range(METER_SEGMENTS):
            x0 = i * (seg_width + gap)
            self._segments.append(
                self.create_rectangle(x0, 0, x0 + seg_width, height, fill=METER_OFF, width=0)
            )

    def set_level(self, dbfs: float, peak_dbfs: float) -> None:
        """현재 음량과 최고점을 반영해 칸 색을 갱신한다."""
        filled = round(dbfs_to_ratio(dbfs) * METER_SEGMENTS)
        peak_index = round(dbfs_to_ratio(peak_dbfs) * METER_SEGMENTS) - 1

        for i, rect in enumerate(self._segments):
            if i < filled:
                color = segment_color(i, METER_SEGMENTS)
            elif i == peak_index and peak_index >= 0:
                # 최고점 표시: 소리가 사라진 뒤에도 잠깐 남아서 '방금 얼마나 컸는지' 보여준다
                color = FG_MUTED
            else:
                color = METER_OFF
            self.itemconfig(rect, fill=color)
