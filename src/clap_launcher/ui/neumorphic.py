"""뉴모피즘 부품 — 부드러운 그림자를 가진 패널·버튼·토글.

⚠️ 왜 이런 파일이 필요한가:
Tkinter에는 '그림자'라는 개념이 아예 없다. CSS의 box-shadow 같은 게 없어서
버튼 뒤에 흐릿한 그림자를 깔 방법이 기본 기능에는 없다.

그래서 **그림자가 그려진 이미지를 직접 만들어서** 캔버스에 깔고, 그 위에 글자와
아이콘을 얹는다. 이미지는 크기·모양별로 한 번만 만들어 캐시하므로,
화면이 20fps로 갱신돼도 매번 다시 만들지 않는다.

Pillow(PIL)가 있으면 진짜 가우시안 블러로 부드러운 그림자를 만들고,
없으면 그림자 없이 납작하게 그린다(기능은 그대로 동작한다).
"""

import tkinter as tk

from . import icons, theme

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk
    _HAS_PIL = True
except ImportError:      # Pillow가 없어도 프로그램은 돌아가야 한다
    _HAS_PIL = False

# 만든 그림자 이미지를 재사용하기 위한 보관함.
# 키가 같으면(같은 크기·모양·상태) 이미 만든 이미지를 그대로 쓴다.
_IMAGE_CACHE: dict[tuple, "ImageTk.PhotoImage"] = {}


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _rounded_mask(size: tuple[int, int], radius: int,
                  offset: tuple[int, int] = (0, 0)) -> "Image.Image":
    """둥근 사각형 모양의 흑백 판(마스크)을 만든다. 그림자 계산의 재료."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    left, top = offset
    draw.rounded_rectangle(
        [left, top, left + size[0] - 1 - abs(offset[0]) * 0,
         top + size[1] - 1 - abs(offset[1]) * 0],
        radius=radius, fill=255,
    )
    return mask


def _make_surface(width: int, height: int, radius: int, raised: bool,
                  fill: str, offset: int, blur: int) -> "ImageTk.PhotoImage | None":
    """뉴모피즘 표면 이미지를 만든다.

    Args:
        raised: True면 튀어나온 모양, False면 움푹 들어간 모양
        fill: 표면 자체의 색 (보통 배경과 같은 색)

    Returns:
        Pillow가 없으면 None (그때는 부르는 쪽이 납작하게 그린다)
    """
    if not _HAS_PIL or width < 2 or height < 2:
        return None

    key = (width, height, radius, raised, fill, offset, blur)
    if key in _IMAGE_CACHE:
        return _IMAGE_CACHE[key]

    pad = blur * 2 + offset          # 그림자가 번질 여백
    canvas_size = (width + pad * 2, height + pad * 2)
    base = Image.new("RGB", canvas_size, _hex_to_rgb(theme.BG))
    shape_box = [pad, pad, pad + width - 1, pad + height - 1]

    shape = Image.new("L", canvas_size, 0)
    ImageDraw.Draw(shape).rounded_rectangle(shape_box, radius=radius, fill=255)

    if raised:
        # 튀어나온 모양: 도형 뒤로 두 방향의 그림자를 깐 뒤 도형을 덮는다
        for color, dx, dy in ((theme.DARK, offset, offset),
                              (theme.LIGHT, -offset, -offset)):
            shadow = shape.transform(
                canvas_size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy), fillcolor=0
            ).filter(ImageFilter.GaussianBlur(blur))
            base.paste(Image.new("RGB", canvas_size, _hex_to_rgb(color)), (0, 0), shadow)
        base.paste(Image.new("RGB", canvas_size, _hex_to_rgb(fill)), (0, 0), shape)
    else:
        # 움푹 들어간 모양: 도형을 먼저 깔고, 그 **안쪽에** 그림자를 그린다.
        # 안쪽 그림자 = (도형) - (도형을 살짝 민 것) → 한쪽 가장자리에만 남는 띠
        base.paste(Image.new("RGB", canvas_size, _hex_to_rgb(fill)), (0, 0), shape)
        for color, dx, dy in ((theme.DARK, offset, offset),
                              (theme.LIGHT, -offset, -offset)):
            shifted = shape.transform(
                canvas_size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy), fillcolor=0
            )
            ring = ImageChops.subtract(shape, shifted).filter(ImageFilter.GaussianBlur(blur))
            ring = ImageChops.multiply(ring, shape)   # 도형 밖으로 새어 나가지 않게 자른다
            base.paste(Image.new("RGB", canvas_size, _hex_to_rgb(color)), (0, 0), ring)

    try:
        photo = ImageTk.PhotoImage(base)
    except Exception:
        # 이미지를 Tk에 올리지 못하는 상황(창이 아직 없거나 Tk 이미지 한도 초과 등).
        # 그림자는 어차피 장식이므로, 죽는 대신 None을 돌려주고 납작하게 그리게 한다.
        return None

    _IMAGE_CACHE[key] = photo
    return photo


class NeoSurface(tk.Canvas):
    """뉴모피즘 표면 하나. 패널·버튼·미터가 모두 이걸 바탕으로 만들어진다.

    캔버스를 쓰는 이유: 이미지를 깔고 그 위에 글자와 아이콘을 자유롭게 얹어야 하는데,
    일반 위젯(Frame, Button)으로는 그림자 이미지를 배경으로 깔 수 없다.
    """

    def __init__(self, parent, width: int, height: int, radius: int = theme.RADIUS_SMALL,
                 raised: bool = True, fill: str | None = None, **kwargs) -> None:
        self.pad = theme.SHADOW_BLUR * 2 + theme.SHADOW_OFFSET
        super().__init__(
            parent, width=width + self.pad * 2, height=height + self.pad * 2,
            bg=theme.BG, highlightthickness=0, bd=0, **kwargs,
        )
        self.surface_width = width
        self.surface_height = height
        self.radius = radius
        self.fill_color = fill or theme.BG
        self._raised = raised
        self._image = None
        self._image_id = None
        self._draw_surface()

    def _draw_surface(self) -> None:
        photo = _make_surface(self.surface_width, self.surface_height, self.radius,
                              self._raised, self.fill_color,
                              theme.SHADOW_OFFSET, theme.SHADOW_BLUR)
        if photo is not None:
            self._image = photo      # 참조를 들고 있어야 한다. 안 그러면 가비지 컬렉션돼 사라진다
            if self._image_id is None:
                self._image_id = self.create_image(0, 0, image=photo, anchor="nw")
            else:
                self.itemconfig(self._image_id, image=photo)
            self.tag_lower(self._image_id)
        elif self._image_id is None:
            # Pillow가 없을 때: 그림자 없이 테두리만 있는 납작한 사각형
            self._image_id = self.create_rectangle(
                self.pad, self.pad, self.pad + self.surface_width,
                self.pad + self.surface_height, fill=self.fill_color, outline=theme.DARK,
            )

    def set_raised(self, raised: bool) -> None:
        """튀어나온 모양 ↔ 들어간 모양 전환 (버튼 누름 표현에 쓴다)."""
        if raised != self._raised:
            self._raised = raised
            self._draw_surface()

    # 표면 안쪽 좌표를 쉽게 구하기 위한 도우미
    @property
    def cx(self) -> float:
        return self.pad + self.surface_width / 2

    @property
    def cy(self) -> float:
        return self.pad + self.surface_height / 2


class NeoButton(NeoSurface):
    """뉴모피즘 버튼.

    누르면 **들어간 모양으로 바뀐다.** 뉴모피즘에서는 색이 아니라 입체감으로
    상태를 표현하는 게 자연스럽다. 실제 물리 버튼을 누르는 것과 같은 은유다.
    """

    ICON_SIZE = 16
    GAP = 7            # 아이콘과 글자 사이
    SIDE_PADDING = 16

    def __init__(self, parent, text: str = "", icon: str | None = None,
                 command=None, accent: bool = False, width: int | None = None,
                 height: int = 38, **kwargs) -> None:
        from tkinter import font as tkfont

        self.text = text
        self.icon_name = icon
        self.command = command
        self.accent = accent
        self._enabled = True
        self._pressed = False

        self._font = tkfont.Font(font=theme.FONT_BUTTON)
        if width is None:
            width = self._natural_width()

        super().__init__(parent, width=width, height=height,
                         radius=theme.RADIUS_SMALL, raised=True,
                         fill=theme.ACCENT if accent else theme.BG, **kwargs)
        self._items: list[int] = []
        self._render_content()

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _natural_width(self) -> int:
        text_width = self._font.measure(self.text) if self.text else 0
        icon_width = (self.ICON_SIZE + self.GAP) if self.icon_name else 0
        return text_width + icon_width + self.SIDE_PADDING * 2

    # 밖에서 글자색을 직접 지정하고 싶을 때 쓴다 (예: 묶음 버튼의 선택 표시)
    text_color: str | None = None

    def _content_color(self) -> str:
        if not self._enabled:
            return theme.FG_MUTED
        if self.text_color is not None:
            return self.text_color
        return theme.FG_ON_ACCENT if self.accent else theme.FG

    def _render_content(self) -> None:
        """아이콘과 글자를 다시 그린다. 눌린 상태면 1px 내려 그려 눌린 느낌을 준다."""
        for item in self._items:
            self.delete(item)
        self._items = []

        color = self._content_color()
        nudge = 1 if self._pressed else 0
        text_width = self._font.measure(self.text) if self.text else 0
        icon_width = (self.ICON_SIZE + self.GAP) if self.icon_name else 0
        start_x = self.cx - (text_width + icon_width) / 2

        if self.icon_name:
            self._items += icons.draw(
                self, self.icon_name, start_x + self.ICON_SIZE / 2, self.cy + nudge,
                self.ICON_SIZE, color, width=2,
            )
        if self.text:
            self._items.append(self.create_text(
                start_x + icon_width, self.cy + nudge, text=self.text, anchor="w",
                fill=color, font=theme.FONT_BUTTON,
            ))

    # ── 상태 ──────────────────────────────────────────────
    def configure_state(self, enabled: bool) -> None:
        """버튼을 켜고 끈다. (ttk의 state= 대신 쓰는 이 위젯의 방식)

        꺼진 강조 버튼은 **배경색까지 평범하게** 되돌린다.
        강조색(파랑)을 그대로 두고 글자만 흐리게 하면 대비가 나빠 글자가 안 읽힌다.
        """
        if enabled == self._enabled:
            return
        self._enabled = enabled
        self._pressed = False
        self.fill_color = theme.ACCENT if (self.accent and enabled) else theme.BG
        self._raised = True
        self._draw_surface()
        self._render_content()

    def set_text(self, text: str, icon: str | None = None) -> None:
        """글자와 아이콘을 바꾼다 (듣기 시작 ↔ 듣기 중지처럼)."""
        self.text = text
        if icon is not None:
            self.icon_name = icon
        self._render_content()

    def _on_enter(self, _event=None) -> None:
        if self._enabled:
            self.config(cursor="hand2")

    def _on_leave(self, _event=None) -> None:
        self.config(cursor="")
        if self._pressed:
            self._pressed = False
            self.set_raised(True)
            self._render_content()

    def _on_press(self, _event=None) -> None:
        if not self._enabled:
            return
        self._pressed = True
        self.set_raised(False)     # 눌리면 움푹 들어간다
        self._render_content()

    def _on_release(self, _event=None) -> None:
        if not self._enabled or not self._pressed:
            return
        self._pressed = False
        self.set_raised(True)
        self._render_content()
        if self.command is not None:
            self.command()


class NeoToggle(tk.Canvas):
    """켜고 끄는 스위치. 체크박스 대신 쓴다.

    체크박스보다 스위치를 쓴 이유: '화면 잠금을 풀면 자동으로 듣기'처럼
    **기능을 켜고 끄는** 설정이라, 목록에서 항목을 고르는 체크박스보다 의미가 잘 맞는다.
    """

    TRACK_WIDTH = 46
    TRACK_HEIGHT = 24
    KNOB_MARGIN = 3

    def __init__(self, parent, text: str, value: bool = False, command=None, **kwargs):
        self.pad = theme.SHADOW_BLUR * 2 + theme.SHADOW_OFFSET
        from tkinter import font as tkfont
        font = tkfont.Font(font=theme.FONT_BODY)
        total_width = self.pad * 2 + self.TRACK_WIDTH + 10 + font.measure(text)

        super().__init__(parent, width=total_width, height=self.TRACK_HEIGHT + self.pad * 2,
                         bg=theme.BG, highlightthickness=0, bd=0, **kwargs)
        self.value = value
        self.command = command

        self._track_image = _make_surface(
            self.TRACK_WIDTH, self.TRACK_HEIGHT, self.TRACK_HEIGHT // 2, False,
            theme.BG_SUNKEN, theme.SHADOW_OFFSET - 1, theme.SHADOW_BLUR - 2)
        if self._track_image is not None:
            self.create_image(0, 0, image=self._track_image, anchor="nw")

        self._fill = self.create_oval(0, 0, 0, 0, outline="", fill=theme.ACCENT)
        self._knob = self.create_oval(0, 0, 0, 0, outline=theme.DARK, fill=theme.BG)
        self.create_text(self.pad + self.TRACK_WIDTH + 10, self.pad + self.TRACK_HEIGHT / 2,
                         text=text, anchor="w", fill=theme.FG, font=theme.FONT_BODY)

        self._redraw()
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda _e: self.config(cursor="hand2"))
        self.bind("<Leave>", lambda _e: self.config(cursor=""))

    def _redraw(self) -> None:
        size = self.TRACK_HEIGHT - self.KNOB_MARGIN * 2
        left = self.pad + self.KNOB_MARGIN
        right = self.pad + self.TRACK_WIDTH - self.KNOB_MARGIN - size
        x = right if self.value else left
        top = self.pad + self.KNOB_MARGIN

        # 켜져 있으면 트랙 안쪽을 강조색으로 채운다
        if self.value:
            self.coords(self._fill, self.pad + 2, self.pad + 2,
                        self.pad + self.TRACK_WIDTH - 2, self.pad + self.TRACK_HEIGHT - 2)
        else:
            self.coords(self._fill, 0, 0, 0, 0)   # 화면 밖으로 치워 감춘다

        self.coords(self._knob, x, top, x + size, top + size)
        self.itemconfig(self._knob, fill=theme.LIGHT if self.value else theme.BG,
                        outline=theme.LIGHT if self.value else theme.DARK)
        self.tag_raise(self._knob)

    def _on_click(self, _event=None) -> None:
        self.value = not self.value
        self._redraw()
        if self.command is not None:
            self.command()

    def set(self, value: bool) -> None:
        self.value = value
        self._redraw()


class NeoSegmented(tk.Frame):
    """여러 값 중 하나를 고르는 가로 버튼 묶음. 고른 것만 움푹 들어가 보인다.

    드롭다운 대신 쓴 이유: 선택지가 5개 안팎이면 펼쳐 보이는 편이 빠르고,
    '눌려 있는 것이 지금 값'이라는 표현이 뉴모피즘과 잘 맞는다.
    """

    def __init__(self, parent, options: list[tuple[str, float]], value: float,
                 command=None, **kwargs) -> None:
        """
        Args:
            options: (보여줄 글자, 실제 값) 목록
            value: 처음 선택된 값
        """
        super().__init__(parent, bg=theme.BG, **kwargs)
        self.value = value
        self.command = command
        self._buttons: dict[float, NeoButton] = {}

        for label, option_value in options:
            button = NeoButton(
                self, text=label, height=30, width=max(42, len(label) * 11 + 18),
                command=lambda v=option_value: self._select(v),
            )
            button.pack(side="left", padx=0)
            self._buttons[option_value] = button
        self._refresh()

    def _select(self, value: float) -> None:
        self.value = value
        self._refresh()
        if self.command is not None:
            self.command()

    def _refresh(self) -> None:
        """고른 것은 움푹 들어가고 글자도 강조색이 된다.

        입체감만으로 구분하면 작은 버튼에서는 차이가 잘 안 보인다.
        색까지 함께 바꿔야 한눈에 들어온다.
        """
        for option_value, button in self._buttons.items():
            selected = option_value == self.value
            button.set_raised(not selected)
            button.text_color = theme.ACCENT if selected else theme.FG_MUTED
            button._render_content()


class IconLabel(tk.Canvas):
    """아이콘 + 글자 한 줄. 상태 표시에 쓴다.

    ttk.Label 은 아이콘을 함께 그릴 수 없어서(이미지를 붙이려면 파일이 필요하다)
    캔버스로 만들었다. 아이콘과 글자 색이 항상 함께 바뀌므로 상태 표현이 일관된다.
    """

    def __init__(self, parent, width: int, icon: str = "dot", text: str = "",
                 color: str = theme.FG, font=theme.FONT_BODY, icon_size: int = 18,
                 **kwargs) -> None:
        height = max(icon_size, 20) + 6
        super().__init__(parent, width=width, height=height, bg=theme.BG,
                         highlightthickness=0, bd=0, **kwargs)
        self._width = width
        self._icon_size = icon_size
        self._font = font
        self._items: list[int] = []
        self.set(text, icon, color)

    def set(self, text: str, icon: str | None = None, color: str = theme.FG) -> None:
        for item in self._items:
            self.delete(item)
        self._items = []

        middle = self.winfo_reqheight() / 2
        x = 2
        if icon:
            self._items += icons.draw(self, icon, x + self._icon_size / 2, middle,
                                      self._icon_size, color, width=2)
            x += self._icon_size + 8
        self._items.append(self.create_text(x, middle, text=text, anchor="w",
                                            fill=color, font=self._font))


class NeoPanel(tk.Frame):
    """내용을 담는 움푹 들어간 패널. 목록·로그처럼 '안에 담긴' 것들에 쓴다.

    NeoSurface 와 달리 **자식 위젯을 담을 수 있어야** 해서 Frame 위에 캔버스를 깔았다.
    """

    def __init__(self, parent, width: int, height: int,
                 radius: int = theme.RADIUS_LARGE, padding: int = 12, **kwargs) -> None:
        super().__init__(parent, bg=theme.BG, **kwargs)
        self.pad = theme.SHADOW_BLUR * 2 + theme.SHADOW_OFFSET

        self._canvas = tk.Canvas(
            self, width=width + self.pad * 2, height=height + self.pad * 2,
            bg=theme.BG, highlightthickness=0, bd=0,
        )
        self._canvas.pack()
        self._image = _make_surface(width, height, radius, False, theme.BG_SUNKEN,
                                    theme.SHADOW_OFFSET, theme.SHADOW_BLUR)
        if self._image is not None:
            self._canvas.create_image(0, 0, image=self._image, anchor="nw")
        else:
            self._canvas.create_rectangle(self.pad, self.pad, self.pad + width,
                                          self.pad + height, fill=theme.BG_SUNKEN,
                                          outline=theme.DARK)

        # 자식 위젯이 들어갈 자리 (패널 안쪽 여백을 뺀 영역)
        self.body = tk.Frame(self._canvas, bg=theme.BG_SUNKEN)
        self._canvas.create_window(
            self.pad + padding, self.pad + padding, anchor="nw", window=self.body,
            width=width - padding * 2, height=height - padding * 2,
        )
