"""앱 아이콘과 이름 테스트.

아이콘이 '예쁜지'는 자동으로 판단할 수 없다. 대신 **패키징할 때 사고가 나는 지점**을 막는다.
  ⭐ .ico 안에 작은 크기까지 들어 있는가 (없으면 작업표시줄에서 흐려진다)
  ⭐ 파일이 빠졌을 때 창이 안 뜨는 일은 없는가

이름은 여러 파일에 흩어져 있어서 한 군데만 고치고 넘어가기 쉽다. 그래서 묶어서 확인한다.
"""

from pathlib import Path

import pytest

from clap_launcher import autostart, settings
from clap_launcher.ui import app as app_module
from clap_launcher.ui import icons, theme, tray

APP_NAME = "ClapDesk"
ASSETS = Path(__file__).resolve().parents[1] / "assets"


class TestIconAssets:
    def test_아이콘_파일이_저장소에_있다(self):
        """⭐ 다른 기기로 옮길 때 커밋된 파일만 따라온다. 빌드 자산은 반드시 커밋돼 있어야 한다."""
        assert (ASSETS / "icon.ico").is_file(), "assets/icon.ico 가 없다 (python tools/make_icon.py)"
        assert (ASSETS / "icon.png").is_file()

    def test_ico에_작은_크기까지_들어_있다(self):
        """⭐ 256px 하나만 담으면 Windows 가 16px 로 대충 줄여 흐릿해진다."""
        pillow = pytest.importorskip("PIL.Image")
        with pillow.open(ASSETS / "icon.ico") as image:
            sizes = {size[0] for size in image.info.get("sizes", set())}
        for needed in (16, 32, 48, 256):
            assert needed in sizes, f"{needed}px 이 .ico 에 없다: {sorted(sizes)}"

    def test_창_아이콘_경로를_찾는다(self):
        found = app_module.app_icon_path()
        assert found is not None and found.name == "icon.ico"

    def test_파일이_없어도_경로_조회가_죽지_않는다(self, monkeypatch, tmp_path):
        """exe 로 묶을 때 자산이 빠지는 사고는 흔하다. 그때 창까지 못 뜨면 안 된다."""
        monkeypatch.setattr(app_module, "__file__", str(tmp_path / "a/b/c/app.py"))
        monkeypatch.setattr(app_module.sys, "_MEIPASS", str(tmp_path), raising=False)
        assert app_module.app_icon_path() is None


class TestBadge:
    def test_배지를_그린다(self):
        image = icons.render_badge(64, fill=theme.ACCENT, fill_bottom=theme.ACCENT_DARK)
        assert image is not None
        assert image.size == (64, 64)
        assert image.mode == "RGBA"

    def test_모서리는_투명하다(self):
        """둥근 사각형이라 네 귀퉁이는 비어 있어야 한다. 꽉 찬 사각형이면 촌스럽다."""
        image = icons.render_badge(64, fill=theme.ACCENT)
        assert image.getpixel((0, 0))[3] < 40          # 왼쪽 위 귀퉁이 = 거의 투명
        assert image.getpixel((32, 32))[3] > 200       # 가운데 = 불투명

    def test_너무_작으면_만들지_않는다(self):
        assert icons.render_badge(4, fill=theme.ACCENT) is None

    def test_없는_마크를_주면_None(self):
        assert icons.render_badge(64, fill=theme.ACCENT, mark="없는아이콘") is None


class TestName:
    """이름이 흩어져 있어 한 군데만 고치고 넘어가기 쉽다. 한자리에서 확인한다."""

    def test_창_제목(self):
        assert app_module.WINDOW_TITLE == APP_NAME

    def test_트레이_설명(self):
        assert tray.status_text(True).startswith(APP_NAME)

    def test_설정_폴더(self):
        assert settings.APP_DIR_NAME == APP_NAME

    def test_자동_실행_등록_이름(self):
        assert autostart.VALUE_NAME == APP_NAME

    def test_예전_이름이_남아_있다(self):
        """⭐ 이걸 지우면 예전 사용자의 설정과 자동 실행 등록이 고아가 된다."""
        assert settings.LEGACY_APP_DIR_NAME == "ClappingSetup"
        assert "ClappingSetup" in autostart.LEGACY_VALUE_NAMES
