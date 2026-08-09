"""앱 아이콘(assets/icon.ico) 을 만든다.

왜 그림판이 아니라 스크립트인가:
  · 테마 색이 바뀌면 다시 돌리기만 하면 된다 (손으로 그린 파일은 색을 못 따라온다)
  · 화면 안 아이콘과 **같은 도형**을 쓴다 (ui/icons.py 의 clap 마크를 그대로 가져온다)
  · 저장소에 그림 편집기 없이도 재현 가능한 상태로 남는다

쓰는 법:
    python tools/make_icon.py

만들어지는 것:
    assets/icon.ico         exe·창·작업표시줄용 (16~256px 을 한 파일에 담는다)
    assets/icon.png         256px 단일 이미지 (README·스토어 등)
    assets/icon_preview.png 크기별로 어떻게 보이는지 한눈에 확인용
"""

import sys
from pathlib import Path

# 저장소 안의 패키지를 그대로 쓴다. 경로를 코드에 박지 않기 위해 이 파일 위치에서 계산한다.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

from clap_launcher.ui import icons, theme  # noqa: E402

# Windows 가 상황에 따라 골라 쓰는 크기들. 작은 것까지 넣어야 트레이·목록에서 흐려지지 않는다.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
MASTER_SIZE = 512      # 이 크기로 한 번 그린 뒤 줄여서 각 크기를 만든다

OUT_DIR = ROOT / "assets"


def build_master() -> Image.Image:
    """가장 큰 원본 이미지 하나. 나머지는 전부 이걸 줄여서 만든다."""
    image = icons.render_badge(MASTER_SIZE, fill=theme.ACCENT,
                               fill_bottom=theme.ACCENT_DARK, mark="clap")
    if image is None:
        raise SystemExit("Pillow 가 없어 아이콘을 만들 수 없습니다. pip install Pillow")
    return image


def build_preview(master: Image.Image) -> Image.Image:
    """크기별로 나란히 놓은 확인용 이미지.

    16px 에서 뭉개지지 않는지 **눈으로** 봐야 한다. 256px 만 보고 정하면
    정작 작업표시줄에서 형체를 알아볼 수 없는 아이콘이 나온다.
    """
    sizes = [256, 128, 64, 48, 32, 24, 16]
    gap = 16
    width = sum(sizes) + gap * (len(sizes) + 1)
    canvas = Image.new("RGBA", (width, 256 + gap * 2), (232, 235, 242, 255))

    x = gap
    for size in sizes:
        small = master.resize((size, size), Image.LANCZOS)
        canvas.paste(small, (x, gap + (256 - size) // 2), small)
        x += size + gap
    return canvas


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    master = build_master()

    # ⚠️ Pillow 의 ico 저장은 sizes 를 주면 알아서 여러 장을 담아준다.
    #    큰 이미지 하나만 담으면 작은 크기에서 Windows 가 대충 줄여 흐려진다.
    ico_path = OUT_DIR / "icon.ico"
    master.save(ico_path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])

    png_path = OUT_DIR / "icon.png"
    master.resize((256, 256), Image.LANCZOS).save(png_path, format="PNG")

    preview_path = OUT_DIR / "icon_preview.png"
    build_preview(master).save(preview_path, format="PNG")

    for path in (ico_path, png_path, preview_path):
        print(f"만듦: {path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
