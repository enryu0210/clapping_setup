"""아이콘과 뉴모피즘 부품 테스트.

화면이 '예쁜지'는 자동으로 판단할 수 없지만, **깨지지 않는지**는 확인할 수 있다.
아이콘 하나가 잘못된 좌표를 쓰면 그 화면 전체가 뜨지 않으므로,
모든 아이콘을 실제로 한 번씩 그려 본다.
"""

import tkinter as tk

import pytest

from clap_launcher.ui import icons, theme
from clap_launcher.ui.neumorphic import _make_surface


@pytest.fixture(scope="module")
def root():
    """숨긴 Tk 창 하나. 캔버스를 만들려면 창이 있어야 한다."""
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip("화면이 없는 환경이라 Tk를 띄울 수 없습니다")
    window.withdraw()
    yield window
    window.destroy()


class TestIcons:
    @pytest.mark.parametrize("name", icons.AVAILABLE)
    def test_모든_아이콘이_그려진다(self, root, name):
        """하나라도 좌표 계산이 잘못되면 그 화면이 통째로 안 뜬다."""
        canvas = tk.Canvas(root, width=40, height=40)
        ids = icons.draw(canvas, name, 20, 20, 24, theme.FG, width=2)
        assert ids, f"{name} 아이콘이 아무것도 그리지 않았다"
        assert all(isinstance(item, int) for item in ids)

    @pytest.mark.parametrize("size", [12, 16, 24, 48])
    def test_어떤_크기로도_그려진다(self, root, size):
        canvas = tk.Canvas(root, width=80, height=80)
        assert icons.draw(canvas, "clap", 40, 40, size, theme.ACCENT)

    def test_없는_아이콘은_바로_알려준다(self, root):
        """조용히 빈 자리를 남기면 원인을 못 찾는다."""
        canvas = tk.Canvas(root, width=40, height=40)
        with pytest.raises(KeyError):
            icons.draw(canvas, "없는아이콘", 20, 20, 24, theme.FG)

    def test_아이콘_이름_목록이_실제와_일치한다(self, root):
        canvas = tk.Canvas(root, width=40, height=40)
        for name in icons.AVAILABLE:
            icons.draw(canvas, name, 20, 20, 20, theme.FG)


class TestNeumorphicSurface:
    def test_튀어나온_표면과_들어간_표면_모두_만들어진다(self, root):
        raised = _make_surface(100, 40, 10, True, theme.BG, 3, 5)
        inset = _make_surface(100, 40, 10, False, theme.BG_SUNKEN, 3, 5)
        if raised is None:
            pytest.skip("Pillow가 없어 그림자를 만들 수 없습니다(기능은 정상 동작)")
        assert raised.width() == inset.width() > 100   # 그림자 여백만큼 더 크다

    def test_같은_모양은_다시_만들지_않는다(self, root):
        """20fps로 갱신되는 화면에서 매번 이미지를 만들면 느려진다."""
        first = _make_surface(80, 30, 8, True, theme.BG, 3, 5)
        second = _make_surface(80, 30, 8, True, theme.BG, 3, 5)
        if first is None:
            pytest.skip("Pillow 없음")
        assert first is second, "같은 조건인데 이미지를 새로 만들었다(캐시 실패)"

    def test_아주_작은_크기도_죽지_않는다(self, root):
        """창을 줄이면 위젯 크기가 0에 가까워질 수 있다."""
        assert _make_surface(1, 1, 4, True, theme.BG, 3, 5) is None


class TestWithoutPillow:
    """⭐ Pillow가 없어도 프로그램은 돌아야 한다 (그림자만 없어진다).

    Pillow는 그림자를 만드는 데만 쓰는 '장식용' 의존성이다.
    설치가 안 된 환경에서 창이 아예 안 뜨면 곤란하므로 그 경로를 직접 검증한다.
    """

    @pytest.fixture
    def no_pillow(self, monkeypatch):
        from clap_launcher.ui import neumorphic
        monkeypatch.setattr(neumorphic, "_HAS_PIL", False)

    def test_그림자_없이는_None을_돌려준다(self, root, no_pillow):
        assert _make_surface(100, 40, 10, True, theme.BG, 3, 5) is None

    def test_버튼이_그래도_만들어진다(self, root, no_pillow):
        from clap_launcher.ui.neumorphic import NeoButton

        clicked = []
        button = NeoButton(root, text="테스트", icon="check",
                           command=lambda: clicked.append(True))
        button._on_press()
        button._on_release()
        assert clicked == [True], "그림자가 없어도 버튼은 눌려야 한다"

    def test_패널과_토글도_만들어진다(self, root, no_pillow):
        from clap_launcher.ui.neumorphic import NeoPanel, NeoToggle

        assert NeoPanel(root, width=200, height=80) is not None
        toggle = NeoToggle(root, text="테스트", value=False)
        toggle._on_click()
        assert toggle.value is True

    def test_음량_막대도_만들어진다(self, root, no_pillow):
        from clap_launcher.ui.widgets import LevelMeter

        meter = LevelMeter(root)
        meter.set_level(-20.0, -10.0)     # 죽지 않으면 통과


def test_테마_색이_모두_유효한_형식이다():
    """오타 난 색 코드는 위젯을 만들 때 가서야 터진다. 미리 잡는다."""
    color_names = [n for n in dir(theme) if n.isupper() and isinstance(getattr(theme, n), str)]
    colors = [getattr(theme, n) for n in color_names if getattr(theme, n).startswith("#")]
    assert colors, "테마에 색이 하나도 없다"
    for color in colors:
        assert len(color) == 7, f"잘못된 색 코드: {color}"
        int(color[1:], 16)      # 16진수로 못 읽으면 여기서 예외가 난다
