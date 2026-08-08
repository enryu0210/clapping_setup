"""아이콘 — 이모지 대신 캔버스에 직접 그리는 선 아이콘.

왜 이모지를 걷어냈나:
  · Windows 이모지는 알록달록해서 뉴모피즘의 차분한 톤과 따로 논다
  · 글꼴에 따라 흑백으로 나오거나 아예 네모(□)로 깨진다
  · 크기·색을 마음대로 못 맞춘다

왜 이미지 파일이 아니라 직접 그리나:
  · 파일을 안 들고 다녀도 되고(패키징이 단순해진다), 라이선스 문제도 없다
  · **색을 인자로 받으므로** 테마 색이 바뀌면 아이콘 색도 저절로 따라온다
  · 어떤 크기로 그려도 흐려지지 않는다

모든 아이콘은 (cx, cy)를 중심으로 한 변이 size인 정사각형 안에 그려진다.
"""

import tkinter as tk

_ROUND = {"capstyle": tk.ROUND, "joinstyle": tk.ROUND}


def _mic(c, x, y, s, color, w):
    """마이크 — 캡슐 모양 몸통 + U자 받침."""
    body_w = s * 0.30
    ids = [
        # 굵은 선에 둥근 끝을 주면 캡슐 모양이 된다 (도형을 여러 개 그릴 필요가 없다)
        c.create_line(x, y - s * 0.30, x, y - s * 0.02,
                      fill=color, width=body_w, capstyle=tk.ROUND),
        c.create_arc(x - s * 0.28, y - s * 0.28, x + s * 0.28, y + s * 0.28,
                     start=200, extent=140, style=tk.ARC, outline=color, width=w),
        c.create_line(x, y + s * 0.28, x, y + s * 0.42, fill=color, width=w, **_ROUND),
        c.create_line(x - s * 0.18, y + s * 0.42, x + s * 0.18, y + s * 0.42,
                      fill=color, width=w, **_ROUND),
    ]
    return ids


def _target(c, x, y, s, color, w):
    """과녁 — 보정(맞춰 나가는 것)을 뜻한다."""
    return [
        c.create_oval(x - s * 0.42, y - s * 0.42, x + s * 0.42, y + s * 0.42,
                      outline=color, width=w),
        c.create_oval(x - s * 0.20, y - s * 0.20, x + s * 0.20, y + s * 0.20,
                      outline=color, width=w),
        c.create_oval(x - s * 0.05, y - s * 0.05, x + s * 0.05, y + s * 0.05,
                      fill=color, outline=color),
    ]


def _headphones(c, x, y, s, color, w):
    """헤드폰 — '듣는 중'."""
    cup = s * 0.22
    return [
        c.create_arc(x - s * 0.40, y - s * 0.38, x + s * 0.40, y + s * 0.30,
                     start=20, extent=140, style=tk.ARC, outline=color, width=w),
        c.create_line(x - s * 0.36, y + s * 0.02, x - s * 0.36, y + s * 0.26,
                      fill=color, width=cup, capstyle=tk.ROUND),
        c.create_line(x + s * 0.36, y + s * 0.02, x + s * 0.36, y + s * 0.26,
                      fill=color, width=cup, capstyle=tk.ROUND),
    ]


def _standby(c, x, y, s, color, w):
    """대기(전원) — 위가 트인 원 + 세로 막대. '지금은 쉬는 중'."""
    return [
        c.create_arc(x - s * 0.36, y - s * 0.30, x + s * 0.36, y + s * 0.42,
                     start=65, extent=-310, style=tk.ARC, outline=color, width=w),
        c.create_line(x, y - s * 0.42, x, y - s * 0.02, fill=color, width=w, **_ROUND),
    ]


def _clock(c, x, y, s, color, w):
    """시계 — 남은 시간."""
    return [
        c.create_oval(x - s * 0.40, y - s * 0.40, x + s * 0.40, y + s * 0.40,
                      outline=color, width=w),
        c.create_line(x, y - s * 0.20, x, y, fill=color, width=w, **_ROUND),
        c.create_line(x, y, x + s * 0.20, y + s * 0.10, fill=color, width=w, **_ROUND),
    ]


def _clap(c, x, y, s, color, w):
    """박수 — 맞부딪히는 두 손바닥 + 위로 튀는 소리.

    손가락까지 그리면 작은 크기에서 뭉개진다.
    '기울어진 두 손바닥이 가운데서 만나고, 소리가 위로 튄다'로 단순화했다.
    """
    palm = s * 0.17
    ids = [
        # 왼손: 오른쪽 위로 기울어진 두툼한 선
        c.create_line(x - s * 0.34, y + s * 0.30, x - s * 0.08, y + s * 0.04,
                      fill=color, width=palm, capstyle=tk.ROUND),
        # 오른손: 왼쪽 위로 기울어진 선 (가운데서 만난다)
        c.create_line(x + s * 0.34, y + s * 0.30, x + s * 0.08, y + s * 0.04,
                      fill=color, width=palm, capstyle=tk.ROUND),
    ]
    # 부딪힌 지점에서 위로 튀는 소리 세 줄
    for dx, top in ((-0.20, 0.34), (0.0, 0.44), (0.20, 0.34)):
        ids.append(c.create_line(x + s * dx * 0.7, y - s * 0.14,
                                 x + s * dx, y - s * top,
                                 fill=color, width=max(1, w - 1), **_ROUND))
    return ids


def _sparkle(c, x, y, s, color, w):
    """반짝임 — 성공·발동."""
    ids = []
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        ids.append(c.create_line(x + dx * s * 0.14, y + dy * s * 0.14,
                                 x + dx * s * 0.42, y + dy * s * 0.42,
                                 fill=color, width=w, **_ROUND))
    for dx, dy in ((-1, -1), (1, 1), (-1, 1), (1, -1)):
        ids.append(c.create_line(x + dx * s * 0.12, y + dy * s * 0.12,
                                 x + dx * s * 0.26, y + dy * s * 0.26,
                                 fill=color, width=max(1, w - 1), **_ROUND))
    return ids


def _check(c, x, y, s, color, w):
    """체크 — 확인·완료."""
    return [c.create_line(x - s * 0.32, y + s * 0.02, x - s * 0.08, y + s * 0.26,
                          x + s * 0.34, y - s * 0.28, fill=color, width=w, **_ROUND)]


def _warning(c, x, y, s, color, w):
    """경고 — 삼각형 + 느낌표."""
    return [
        c.create_polygon(x, y - s * 0.40, x + s * 0.42, y + s * 0.32,
                         x - s * 0.42, y + s * 0.32,
                         outline=color, fill="", width=w, joinstyle=tk.ROUND),
        c.create_line(x, y - s * 0.14, x, y + s * 0.08, fill=color, width=w, **_ROUND),
        c.create_line(x, y + s * 0.21, x, y + s * 0.22, fill=color, width=w, **_ROUND),
    ]


def _close(c, x, y, s, color, w):
    """X — 취소·거부."""
    return [
        c.create_line(x - s * 0.28, y - s * 0.28, x + s * 0.28, y + s * 0.28,
                      fill=color, width=w, **_ROUND),
        c.create_line(x + s * 0.28, y - s * 0.28, x - s * 0.28, y + s * 0.28,
                      fill=color, width=w, **_ROUND),
    ]


def _refresh(c, x, y, s, color, w):
    """새로고침 — 열린 원 + 화살촉."""
    return [
        c.create_arc(x - s * 0.34, y - s * 0.34, x + s * 0.34, y + s * 0.34,
                     start=60, extent=280, style=tk.ARC, outline=color, width=w),
        c.create_line(x + s * 0.17, y - s * 0.40, x + s * 0.19, y - s * 0.24,
                      x + s * 0.35, y - s * 0.27, fill=color, width=w, **_ROUND),
    ]


def _undo(c, x, y, s, color, w):
    """되돌리기 — 왼쪽으로 도는 화살표."""
    return [
        c.create_arc(x - s * 0.34, y - s * 0.24, x + s * 0.34, y + s * 0.40,
                     start=100, extent=200, style=tk.ARC, outline=color, width=w),
        c.create_line(x - s * 0.34, y - s * 0.34, x - s * 0.34, y - s * 0.06,
                      fill=color, width=w, **_ROUND),
        c.create_line(x - s * 0.34, y - s * 0.06, x - s * 0.08, y - s * 0.06,
                      fill=color, width=w, **_ROUND),
    ]


def _stop(c, x, y, s, color, w):
    """정지 — 둥근 사각형."""
    return [c.create_rectangle(x - s * 0.24, y - s * 0.24, x + s * 0.24, y + s * 0.24,
                               fill=color, outline=color, width=w)]


def _play(c, x, y, s, color, w):
    """시작 — 삼각형."""
    return [c.create_polygon(x - s * 0.20, y - s * 0.28, x - s * 0.20, y + s * 0.28,
                             x + s * 0.28, y, fill=color, outline=color,
                             width=w, joinstyle=tk.ROUND)]


def _unlock(c, x, y, s, color, w):
    """잠금 해제 — 몸통 + 열린 고리."""
    return [
        c.create_rectangle(x - s * 0.28, y - s * 0.04, x + s * 0.28, y + s * 0.36,
                           outline=color, width=w),
        c.create_arc(x - s * 0.04, y - s * 0.40, x + s * 0.40, y + s * 0.04,
                     start=90, extent=160, style=tk.ARC, outline=color, width=w),
    ]


def _hourglass(c, x, y, s, color, w):
    """모래시계 — 기다리는 중."""
    return [
        c.create_line(x - s * 0.26, y - s * 0.36, x + s * 0.26, y - s * 0.36,
                      fill=color, width=w, **_ROUND),
        c.create_line(x - s * 0.26, y + s * 0.36, x + s * 0.26, y + s * 0.36,
                      fill=color, width=w, **_ROUND),
        c.create_line(x - s * 0.26, y - s * 0.36, x + s * 0.20, y + s * 0.36,
                      fill=color, width=w, **_ROUND),
        c.create_line(x + s * 0.26, y - s * 0.36, x - s * 0.20, y + s * 0.36,
                      fill=color, width=w, **_ROUND),
    ]


def _dot(c, x, y, s, color, w):
    """채운 원 — 상태 표시등."""
    return [c.create_oval(x - s * 0.22, y - s * 0.22, x + s * 0.22, y + s * 0.22,
                          fill=color, outline=color)]


_ICONS = {
    "mic": _mic, "target": _target, "headphones": _headphones, "standby": _standby,
    "clock": _clock, "clap": _clap, "sparkle": _sparkle, "check": _check,
    "warning": _warning, "close": _close, "refresh": _refresh, "undo": _undo,
    "stop": _stop, "play": _play, "unlock": _unlock, "hourglass": _hourglass,
    "dot": _dot,
}

AVAILABLE = tuple(sorted(_ICONS))


def draw(canvas: tk.Canvas, name: str, cx: float, cy: float, size: float,
         color: str, width: int = 2) -> list[int]:
    """캔버스에 아이콘을 그린다.

    Args:
        name: AVAILABLE 에 있는 이름
        cx, cy: 아이콘 중심
        size: 한 변의 길이
        color: 선 색 (테마 색을 그대로 넘기면 된다)
        width: 선 두께

    Returns:
        그려진 도형들의 id 목록. 나중에 지우거나 색을 바꿀 때 쓴다.

    Raises:
        KeyError: 없는 아이콘 이름. 조용히 빈 자리를 남기면 원인을 못 찾으므로 바로 알린다.
    """
    if name not in _ICONS:
        raise KeyError(f"없는 아이콘: {name!r} (쓸 수 있는 것: {', '.join(AVAILABLE)})")
    return _ICONS[name](canvas, cx, cy, size, color, width)
