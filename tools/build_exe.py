"""배포용 exe(ClapDesk.exe)를 만든다.

쓰는 법:
    pip install pyinstaller
    python tools/build_exe.py

결과:
    dist/ClapDesk.exe   — 파이썬이 없는 PC에서도 이것 하나만 있으면 동작한다

왜 명령어를 외우지 않고 스크립트로 두는가:
빌드 옵션 하나만 빠져도 **개발 PC에서는 잘 되는데 남의 PC에서만 안 되는** exe가 나온다.
그런 문제는 원인을 찾기가 정말 어렵다. 그래서 필요한 옵션과 그 이유를 코드에 남긴다.
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "ClapDesk"
# ⚠️ 패키지의 __main__.py 를 직접 넘기면 상대 import 가 깨진다.
#    (ImportError: attempted relative import with no known parent package)
#    자세한 이유는 tools/entry_point.py 의 설명 참고.
ENTRY = ROOT / "tools" / "entry_point.py"
SRC = ROOT / "src"
ICON = ROOT / "assets" / "icon.ico"


def build_args() -> list[str]:
    """PyInstaller 에 넘길 옵션. 각 줄이 왜 필요한지가 이 함수의 핵심이다."""
    # 데이터 파일 구분자는 OS마다 다르다 (Windows ';', 그 외 ':')
    sep = ";" if sys.platform == "win32" else ":"

    return [
        str(ENTRY),
        "--name", APP_NAME,

        # 진입점이 tools/ 에 있으므로 패키지가 있는 src/ 를 따로 알려준다
        "--paths", str(SRC),

        # 파일 하나로 배포한다. 받는 사람이 폴더째 옮길 필요가 없다.
        # (대신 실행할 때마다 임시 폴더에 풀어서 첫 실행이 1~2초 느리다)
        "--onefile",

        # 콘솔 창을 띄우지 않는다. GUI 앱이 검은 창을 달고 뜨면 완성도가 떨어져 보인다.
        # ⚠️ 이 모드에서는 sys.stdout 이 없다. print() 가 죽지 않는지 확인해야 한다
        #    (console.py 에서 대비해 뒀다).
        "--windowed",

        # exe 파일 자체의 아이콘 (탐색기·작업표시줄에서 보인다)
        "--icon", str(ICON),

        # 창 아이콘용으로 .ico 를 exe 안에 넣는다.
        # 위 --icon 은 exe 파일의 겉모습이고, 이건 프로그램이 실행 중에 읽는 파일이다. 둘은 다르다.
        # (ui/app.py 의 app_icon_path 가 sys._MEIPASS 아래에서 찾는다)
        "--add-data", f"{ICON}{sep}assets",

        # ⚠️ sounddevice 는 PortAudio DLL 을 별도 폴더(_sounddevice_data)에 들고 다닌다.
        #    이걸 빠뜨리면 exe 는 뜨는데 **마이크만 안 잡히는** 상태가 된다.
        #    가장 흔한 패키징 사고라 collect-all 로 통째로 담는다.
        "--collect-all", "sounddevice",

        # 트레이 아이콘은 OS별 구현을 실행 시점에 고른다.
        # PyInstaller 가 import 를 따라가지 못해 빠뜨리는 일이 있어 명시한다.
        "--hidden-import", "pystray._win32",

        # 안 쓰는 무거운 것들을 빼서 exe 크기를 줄인다
        *_excludes(),

        # 남아 있는 예전 빌드 찌꺼기 때문에 생기는 이상 동작을 막는다
        "--clean",
        "--noconfirm",

        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]


def _excludes() -> list[str]:
    """exe 에 들어갈 이유가 없는 모듈들."""
    unused = ["pytest", "_pytest", "matplotlib", "scipy", "pandas", "IPython",
              "setuptools", "pip", "tkinter.test", "test"]
    args = []
    for module in unused:
        args += ["--exclude-module", module]
    return args


def main() -> int:
    if not ICON.is_file():
        print(f"❌ 아이콘이 없습니다: {ICON}\n   먼저 python tools/make_icon.py 를 실행하세요.",
              file=sys.stderr)
        return 1

    try:
        import PyInstaller.__main__
    except ImportError:
        print("❌ PyInstaller 가 없습니다.\n   pip install pyinstaller", file=sys.stderr)
        return 1

    # 예전 결과물이 남아 있으면 '빌드가 실패했는데 성공한 줄 아는' 사고가 난다
    target = ROOT / "dist" / f"{APP_NAME}.exe"
    if target.exists():
        target.unlink()

    print(f"빌드를 시작합니다. 몇 분 걸립니다…\n  진입점: {ENTRY.relative_to(ROOT)}")
    PyInstaller.__main__.run(build_args())

    if not target.is_file():
        print("\n❌ exe 가 만들어지지 않았습니다. 위 로그를 확인하세요.", file=sys.stderr)
        return 1

    size_mb = target.stat().st_size / 1024 / 1024
    print(f"\n✅ 완성: {target.relative_to(ROOT)}  ({size_mb:.1f} MB)")
    print("\n다음으로 확인하세요:")
    print("  1. 더블클릭해서 창이 뜨는지")
    print("  2. 마이크가 잡히는지 (음량 막대가 움직이는지)")
    print("  3. **파이썬이 없는 PC**에서 실행되는지 — 개발 PC에서는 항상 잘 됩니다")
    return 0


def clean() -> int:
    """빌드 찌꺼기를 지운다 (python tools/build_exe.py --clean-only)."""
    for folder in ("build", "dist"):
        path = ROOT / folder
        if path.exists():
            shutil.rmtree(path)
            print(f"지움: {folder}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(clean() if "--clean-only" in sys.argv else main())
