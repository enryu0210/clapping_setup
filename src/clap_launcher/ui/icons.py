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

⚠️ 자글자글한 계단 현상을 없앤 방법 (아래 _PilCanvas):
Tk 캔버스에는 **안티앨리어싱이 없다.** 사선과 원을 그리면 가장자리가 계단처럼 보인다.
그래서 아이콘을 캔버스에 직접 그리지 않고, Pillow로 **4배 크기로 그린 뒤 축소**해서
이미지로 얹는다. 축소할 때 여러 픽셀이 섞이면서 가장자리가 부드러워진다.

아이콘 그리는 코드(아래 _mic, _clap ...)는 하나도 고치지 않았다.
Tk 캔버스인 척하는 얇은 어댑터(_PilCanvas)를 대신 넘겨주기 때문이다.
"""

import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageTk
    _HAS_PIL = True
except ImportError:      # Pillow가 없으면 예전처럼 캔버스에 직접 그린다(자글자글하지만 동작한다)
    _HAS_PIL = False

_ROUND = {"capstyle": tk.ROUND, "joinstyle": tk.ROUND}

SUPERSAMPLE = 4          # 몇 배로 크게 그린 뒤 줄일지. 4배면 충분히 매끈하다

# 만든 아이콘 이미지 보관함. 같은 (이름·크기·색·두께)면 다시 만들지 않는다.
# 화면이 20fps로 갱신돼도 이미지를 매번 새로 만들면 느려진다.
_PHOTO_CACHE: dict[tuple, "ImageTk.PhotoImage"] = {}


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


def _list(c, x, y, s, color, w):
    """목록 — 점 세 개 + 줄 세 개. '등록된 프로그램 목록'."""
    ids = []
    for row in (-0.26, 0.0, 0.26):
        ids.append(c.create_oval(x - s * 0.34, y + s * row - s * 0.05,
                                 x - s * 0.24, y + s * row + s * 0.05,
                                 fill=color, outline=color))
        ids.append(c.create_line(x - s * 0.12, y + s * row, x + s * 0.34, y + s * row,
                                 fill=color, width=w, **_ROUND))
    return ids


def _plus(c, x, y, s, color, w):
    """더하기 — 항목 추가."""
    return [
        c.create_line(x, y - s * 0.30, x, y + s * 0.30, fill=color, width=w, **_ROUND),
        c.create_line(x - s * 0.30, y, x + s * 0.30, y, fill=color, width=w, **_ROUND),
    ]


def _trash(c, x, y, s, color, w):
    """휴지통 — 항목 삭제."""
    return [
        c.create_line(x - s * 0.32, y - s * 0.22, x + s * 0.32, y - s * 0.22,
                      fill=color, width=w, **_ROUND),
        c.create_line(x - s * 0.12, y - s * 0.34, x + s * 0.12, y - s * 0.34,
                      fill=color, width=w, **_ROUND),
        # 통 몸통: 아래로 살짝 좁아지는 사다리꼴
        c.create_line(x - s * 0.24, y - s * 0.14, x - s * 0.18, y + s * 0.32,
                      fill=color, width=w, **_ROUND),
        c.create_line(x + s * 0.24, y - s * 0.14, x + s * 0.18, y + s * 0.32,
                      fill=color, width=w, **_ROUND),
        c.create_line(x - s * 0.18, y + s * 0.32, x + s * 0.18, y + s * 0.32,
                      fill=color, width=w, **_ROUND),
    ]


def _arrow_up(c, x, y, s, color, w):
    """위로 — 순서 올리기."""
    return [
        c.create_line(x, y + s * 0.30, x, y - s * 0.30, fill=color, width=w, **_ROUND),
        c.create_line(x - s * 0.22, y - s * 0.08, x, y - s * 0.32, x + s * 0.22, y - s * 0.08,
                      fill=color, width=w, **_ROUND),
    ]


def _arrow_down(c, x, y, s, color, w):
    """아래로 — 순서 내리기."""
    return [
        c.create_line(x, y - s * 0.30, x, y + s * 0.30, fill=color, width=w, **_ROUND),
        c.create_line(x - s * 0.22, y + s * 0.08, x, y + s * 0.32, x + s * 0.22, y + s * 0.08,
                      fill=color, width=w, **_ROUND),
    ]


def _folder(c, x, y, s, color, w):
    """폴더 — 경로 찾아보기."""
    return [
        c.create_line(x - s * 0.34, y + s * 0.26, x - s * 0.34, y - s * 0.24,
                      x - s * 0.06, y - s * 0.24, x + s * 0.02, y - s * 0.12,
                      x + s * 0.34, y - s * 0.12, fill=color, width=w, **_ROUND),
        c.create_line(x - s * 0.34, y + s * 0.26, x + s * 0.34, y + s * 0.26,
                      x + s * 0.34, y - s * 0.12, fill=color, width=w, **_ROUND),
    ]


def _globe(c, x, y, s, color, w):
    """지구 — 웹 주소(url) 항목."""
    return [
        c.create_oval(x - s * 0.34, y - s * 0.34, x + s * 0.34, y + s * 0.34,
                      outline=color, width=w),
        c.create_line(x - s * 0.34, y, x + s * 0.34, y, fill=color, width=w, **_ROUND),
        c.create_oval(x - s * 0.16, y - s * 0.34, x + s * 0.16, y + s * 0.34,
                      outline=color, width=w),
    ]


_ICONS = {
    "mic": _mic, "target": _target, "headphones": _headphones, "standby": _standby,
    "clock": _clock, "clap": _clap, "sparkle": _sparkle, "check": _check,
    "warning": _warning, "close": _close, "refresh": _refresh, "undo": _undo,
    "stop": _stop, "play": _play, "unlock": _unlock, "hourglass": _hourglass,
    "dot": _dot, "list": _list, "plus": _plus, "trash": _trash,
    "arrow_up": _arrow_up, "arrow_down": _arrow_down, "folder": _folder, "globe": _globe,
}

AVAILABLE = tuple(sorted(_ICONS))


# ── Tk 캔버스인 척하는 Pillow 어댑터 ──────────────────────
#
# 위의 아이콘 함수들은 c.create_line(...) 처럼 Tk 캔버스 명령을 쓴다.
# 같은 이름의 메서드를 가진 이 객체를 대신 넘기면, 똑같은 코드가 Pillow 그림으로 나간다.
# 덕분에 아이콘 정의를 두 벌 관리하지 않아도 된다.

class _PilCanvas:
    """Pillow 도화지를 Tk 캔버스처럼 보이게 감싼 것.

    좌표 변환은 하지 않는다. 부르는 쪽에서 이미 4배 확대된 좌표를 넘겨주기 때문이다.
    반환값(도형 id)은 쓰이지 않으므로 0을 돌려준다.
    """

    def __init__(self, draw: "ImageDraw.ImageDraw") -> None:
        self._draw = draw

    @staticmethod
    def _color(value):
        """Tk의 빈 문자열('')은 '칠하지 않음'이라는 뜻이다. Pillow에서는 None."""
        return value if value else None

    def _round_caps(self, points: list[float], color, width: float) -> None:
        """둥근 끝·둥근 모서리를 흉내 낸다.

        Pillow의 line 에는 '둥근 끝(capstyle)' 개념이 없어서, 꼭짓점마다 지름이
        선 두께인 원을 찍어 메운다. 끝점과 꺾이는 지점이 모두 둥글어진다.
        """
        radius = width / 2
        for i in range(0, len(points) - 1, 2):
            x, y = points[i], points[i + 1]
            self._draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)

    def create_line(self, *coords, fill=None, width=1, capstyle=None, joinstyle=None, **_kw):
        points = [float(v) for v in coords]
        color = self._color(fill)
        self._draw.line(points, fill=color, width=int(round(width)), joint="curve")
        if capstyle == tk.ROUND or joinstyle == tk.ROUND:
            self._round_caps(points, color, width)
        return 0

    def create_oval(self, x0, y0, x1, y1, *, fill=None, outline=None, width=1, **_kw):
        self._draw.ellipse([x0, y0, x1, y1], fill=self._color(fill),
                           outline=self._color(outline), width=int(round(width)))
        return 0

    def create_rectangle(self, x0, y0, x1, y1, *, fill=None, outline=None, width=1, **_kw):
        self._draw.rectangle([x0, y0, x1, y1], fill=self._color(fill),
                             outline=self._color(outline), width=int(round(width)))
        return 0

    def create_polygon(self, *coords, fill=None, outline=None, width=1, **_kw):
        points = [float(v) for v in coords]
        if self._color(fill):
            self._draw.polygon(points, fill=fill)
        if self._color(outline):
            # 테두리는 line 으로 직접 그린다. polygon(width=) 은 Pillow 버전을 타서
            # 옛 버전에서 조용히 무시되거나 오류가 난다.
            closed = points + points[:2]
            self._draw.line(closed, fill=outline, width=int(round(width)), joint="curve")
            self._round_caps(closed, outline, width)
        return 0

    def create_arc(self, x0, y0, x1, y1, *, start=0, extent=90, outline=None,
                   width=1, style=None, **_kw):
        """호(arc). ⚠️ Tk와 Pillow는 각도를 재는 방향이 반대다.

        Tk    : 3시 방향에서 **반시계** 방향으로 잰다
        Pillow: 3시 방향에서 **시계** 방향으로 잰다

        그래서 부호를 뒤집어야 하고, extent 가 음수면 방향이 또 한 번 뒤집히므로
        먼저 '시작점 + 양수 크기' 형태로 정리한 뒤 변환한다.
        """
        if extent < 0:
            start, extent = start + extent, -extent
        self._draw.arc([x0, y0, x1, y1], start=-(start + extent), end=-start,
                       fill=self._color(outline), width=int(round(width)))
        return 0


def render_image(name: str, box: int, color: str, width: int = 2):
    """아이콘을 Pillow 이미지로 그린다.

    Tk 바깥에서도 쓸 수 있게 따로 뒀다 — 트레이 아이콘(tray.py)이 이걸 쓴다.
    (트레이는 Tk 위젯이 아니라 순수한 이미지를 요구한다)

    Args:
        box: 결과 이미지의 한 변 길이. 아이콘은 선 두께만큼 여백을 두고 그 안에 그려진다.

    Returns:
        RGBA 이미지 (배경 투명). Pillow가 없거나 실패하면 None.
    """
    if not _HAS_PIL or name not in _ICONS or box < 4:
        return None

    # 크게 그린 뒤 줄인다. 선 두께의 절반이 밖으로 삐져나가 잘리지 않도록 여백을 둔다.
    canvas_size = box * SUPERSAMPLE
    icon_size = (box - width * 2) * SUPERSAMPLE
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))

    center = canvas_size / 2
    try:
        _ICONS[name](_PilCanvas(ImageDraw.Draw(image)), center, center, icon_size,
                     color, width * SUPERSAMPLE)
        return image.resize((box, box), Image.LANCZOS)
    except Exception:
        return None      # 아이콘은 장식이다. 실패해도 프로그램이 죽을 이유는 없다


def render_badge(size: int, fill: str, fill_bottom: str | None = None,
                 mark: str = "clap", mark_color: str = "#ffffff"):
    """앱 아이콘용 '배지'를 그린다 — 색이 꽉 찬 둥근 사각형 + 흰 마크.

    왜 선 아이콘이 아니라 배지인가:
    화면 안에서는 선 아이콘이 뉴모피즘과 잘 어울리지만, **작업표시줄과 트레이에서는
    16px까지 줄어든다.** 그 크기에서 투명 배경의 가는 선은 거의 보이지 않는다.
    색 덩어리로 보여야 다른 아이콘들 사이에서 눈에 띈다.

    Args:
        size: 결과 이미지 한 변 (정사각형)
        fill: 배지 색 (위쪽). 트레이에서는 이 색으로 상태를 표시한다
        fill_bottom: 아래쪽 색. 주면 위→아래 그라데이션이 된다
        mark: 배지 위에 얹을 아이콘 이름
        mark_color: 마크 색

    Returns:
        RGBA 이미지. Pillow가 없으면 None.
    """
    if not _HAS_PIL or mark not in _ICONS or size < 8:
        return None

    ss = SUPERSAMPLE
    big = size * ss
    top_rgb = _hex_to_rgb(fill)
    bottom_rgb = _hex_to_rgb(fill_bottom or fill)

    # 세로 그라데이션: 한 줄짜리 이미지를 만들어 늘리면 픽셀마다 계산할 필요가 없다
    column = Image.new("RGB", (1, big))
    for y in range(big):
        ratio = y / max(1, big - 1)
        column.putpixel((0, y), tuple(
            round(top + (bottom - top) * ratio)
            for top, bottom in zip(top_rgb, bottom_rgb)))
    gradient = column.resize((big, big))

    # 둥근 사각형으로 오려낸다. 모서리 반경은 크기에 비례해야 어떤 크기에서도 같아 보인다.
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, big - 1, big - 1],
                                           radius=int(big * 0.22), fill=255)
    badge = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    badge.paste(gradient, (0, 0), mask)

    # 마크 크기·두께는 **16px 에서 알아볼 수 있는지**를 기준으로 정했다.
    # 더 작게 잡으면(0.58) 트레이에서 형체가 뭉개지고, 더 키우면 모서리에 닿는다.
    try:
        _ICONS[mark](_PilCanvas(ImageDraw.Draw(badge)), big / 2, big / 2,
                     big * 0.70, mark_color, max(2, int(big * 0.07)))
        return badge.resize((size, size), Image.LANCZOS)
    except Exception:
        return None


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _icon_photo(name: str, size: int, color: str, width: int):
    """아이콘 하나를 부드러운 이미지로 만든다. 이미 만든 것은 그대로 재사용한다.

    Returns:
        Tk에 얹을 수 있는 이미지. Pillow가 없거나 만들지 못하면 None.
    """
    if not _HAS_PIL or size < 2:
        return None

    key = (name, size, color, width)
    if key in _PHOTO_CACHE:
        return _PHOTO_CACHE[key]

    image = render_image(name, size + width * 2, color, width)
    if image is None:
        return None
    try:
        photo = ImageTk.PhotoImage(image)
    except Exception:
        # Tk에 이미지를 올리지 못하는 상황(창이 아직 없는 등).
        # 캔버스에 직접 그리는 길로 물러선다.
        return None

    _PHOTO_CACHE[key] = photo
    return photo


def draw(canvas: tk.Canvas, name: str, cx: float, cy: float, size: float,
         color: str, width: int = 2) -> list[int]:
    """캔버스에 아이콘을 그린다.

    Pillow가 있으면 **미리 부드럽게 만들어 둔 이미지**를 얹고,
    없으면 예전처럼 캔버스에 선을 직접 긋는다(자글자글하지만 동작은 한다).

    Args:
        name: AVAILABLE 에 있는 이름
        cx, cy: 아이콘 중심
        size: 한 변의 길이
        color: 선 색 (테마 색을 그대로 넘기면 된다)
        width: 선 두께

    Returns:
        그려진 것들의 id 목록. 나중에 지울 때 쓴다.

    Raises:
        KeyError: 없는 아이콘 이름. 조용히 빈 자리를 남기면 원인을 못 찾으므로 바로 알린다.
    """
    if name not in _ICONS:
        raise KeyError(f"없는 아이콘: {name!r} (쓸 수 있는 것: {', '.join(AVAILABLE)})")

    photo = _icon_photo(name, int(round(size)), color, int(width))
    if photo is None:
        return _ICONS[name](canvas, cx, cy, size, color, width)
    return [canvas.create_image(cx, cy, image=photo, anchor="center")]
