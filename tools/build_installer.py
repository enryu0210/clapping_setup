"""설치본(ClapDesk-Setup-x.y.z.exe)을 만든다.

쓰는 법:
    winget install JRSoftware.InnoSetup     # 처음 한 번만
    python tools/build_installer.py

하는 일:
    1. exe 를 **폴더 형태(--onedir)** 로 굽는다
       (설치형에서는 폴더가 맞다 — 첫 실행이 빠르고 백신 오탐도 줄어든다)
    2. Inno Setup 으로 그 폴더를 설치본 하나로 묶는다

결과:
    dist/ClapDesk-Setup-1.0.0.exe
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clap_launcher import __version__  # noqa: E402

import build_exe  # noqa: E402  (같은 tools/ 폴더에 있다)

ISS = ROOT / "installer" / "ClapDesk.iss"

# Inno Setup 이 설치될 만한 곳들. winget 으로 깔면 사용자 폴더로 들어가는 경우가 많아
# Program Files 만 보면 못 찾는다 (실제로 여기서 헤맸다).
ISCC_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path.home() / "AppData/Local/Programs/Inno Setup 6/ISCC.exe",
]


def find_iscc() -> Path | None:
    """Inno Setup 컴파일러를 찾는다."""
    for candidate in ISCC_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def main() -> int:
    iscc = find_iscc()
    if iscc is None:
        print("❌ Inno Setup 을 찾지 못했습니다.\n"
              "   winget install JRSoftware.InnoSetup\n"
              "   설치 후 다시 실행하세요.", file=sys.stderr)
        return 1

    print("[1/2] exe 를 폴더 형태로 굽습니다…")
    built = build_exe.build(onedir=True)
    if built is None:
        return 1
    print(f"      → {built.parent.relative_to(ROOT)}")

    print(f"\n[2/2] 설치본을 만듭니다… (Inno Setup: {iscc})")
    # 버전은 소스(__init__.py)에서 읽어 넘긴다. 두 군데에 적으면 반드시 어긋난다.
    result = subprocess.run(
        [str(iscc), f"/DAppVersion={__version__}",
         f"/DSourceDir={built.parent}", str(ISS)],
        cwd=str(ISS.parent), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        print(result.stdout[-3000:], file=sys.stderr)
        print(result.stderr[-2000:], file=sys.stderr)
        print("\n❌ 설치본을 만들지 못했습니다.", file=sys.stderr)
        return 1

    setup = ROOT / "dist" / f"ClapDesk-Setup-{__version__}.exe"
    if not setup.is_file():
        print("\n❌ 설치본 파일이 없습니다. 위 로그를 확인하세요.", file=sys.stderr)
        return 1

    size_mb = setup.stat().st_size / 1024 / 1024
    print(f"\n✅ 완성: {setup.relative_to(ROOT)}  ({size_mb:.1f} MB)")
    print("\n설치본이 하는 일:")
    print("  · 사용자 폴더에 설치 (관리자 권한 불필요)")
    print("  · 시작 메뉴 바로가기 + 제거 프로그램 등록")
    print("  · '시작할 때 자동 실행' 체크박스 (기본 켜짐)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
