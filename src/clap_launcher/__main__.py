"""진입점 — `python -m clap_launcher` 로 실행됩니다.

옵션 없이 실행하면 GUI 창이 뜹니다 (일반 사용자용).
아래 옵션들은 문제가 생겼을 때 콘솔에서 확인하는 디버깅용입니다.

  --list-devices : 마이크 목록 보기
  --level        : 콘솔에서 실시간 음량 확인
"""

import argparse
import sys

from . import __version__
from .console import force_utf8_console


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clap-launcher",
        description="박수 두 번(짝짝)으로 업무용 프로그램을 한 번에 실행합니다.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--list-devices", action="store_true",
        help="[디버깅] 사용 가능한 마이크 목록을 콘솔에 출력합니다.",
    )
    parser.add_argument(
        "--level", action="store_true",
        help="[디버깅] 콘솔에서 실시간 음량 미터를 켭니다.",
    )
    parser.add_argument(
        "--reset-setup", action="store_true",
        help="저장된 마이크 선택을 지우고 처음 선택 화면부터 다시 시작합니다.",
    )
    parser.add_argument(
        "--device", default=None,
        help="쓸 마이크를 번호나 이름 일부로 지정합니다. (예: --device 3, --device Wave)",
    )
    parser.add_argument(
        "--duration", type=float, default=None,
        help="지정한 초만큼만 실행하고 종료합니다. (기본: Ctrl+C 전까지 계속)",
    )
    return parser


def _parse_device(raw: str | None) -> int | str | None:
    """--device 값은 숫자면 장치 번호, 아니면 이름 일부로 해석한다."""
    if raw is None:
        return None
    return int(raw) if raw.lstrip("-").isdigit() else raw


def main(argv: list[str] | None = None) -> int:
    """실행 결과를 종료 코드로 반환한다 (0=정상)."""
    force_utf8_console()
    args = _build_parser().parse_args(argv)

    # 무거운 오디오 라이브러리는 실제로 필요할 때만 불러온다.
    # (--version, --help 만 쓰는 경우까지 sounddevice 로딩을 기다릴 이유가 없다)
    from .audio.listener import AudioDeviceError, list_input_devices

    try:
        if args.list_devices:
            print("사용 가능한 입력 장치:")
            for index, name in list_input_devices():
                print(f"  [{index:3d}] {name}")
            print("\n같은 마이크가 여러 번 보이는 것은 정상입니다(드라이버 방식별로 하나씩).")
            return 0

        if args.level:
            from .ui.level_meter import run_level_meter
            return run_level_meter(_parse_device(args.device), args.duration)

        if args.reset_setup:
            from .settings import Settings, save_settings
            save_settings(Settings())
            print("마이크 선택을 초기화했습니다. 다음 실행 때 선택 화면이 다시 나옵니다.")
            return 0

    except AudioDeviceError as exc:
        # 마이크 문제는 사용자가 직접 고칠 수 있는 문제이므로,
        # 파이썬 traceback 대신 해결 방법이 담긴 메시지만 보여준다.
        print(f"\n❌ {exc}", file=sys.stderr)
        return 1

    # 옵션이 없으면 GUI를 띄운다 (일반 사용자가 실행하는 경로)
    return _run_gui()


def _run_gui() -> int:
    """GUI를 띄운다. tkinter가 없는 환경도 있으므로 그때는 안내를 남긴다."""
    try:
        from .ui.app import run_gui
    except ImportError as exc:
        # 리눅스 배포판 등에서 파이썬만 깔고 tk를 안 깐 경우가 있다.
        print(
            f"❌ 화면을 띄우는 데 필요한 tkinter를 불러오지 못했습니다: {exc}\n"
            "   콘솔에서 확인하려면 다음을 써보세요:\n"
            "     python -m clap_launcher --level",
            file=sys.stderr,
        )
        return 1
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
