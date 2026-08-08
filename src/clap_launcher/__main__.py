"""진입점 — `python -m clap_launcher` 로 실행됩니다.

현재 가능한 것 (M1):
  --list-devices : 마이크 목록 보기
  --level        : 실시간 음량 미터 (마이크가 들리는지 확인)

앞으로 붙을 것:
  M3까지 완성되면 옵션 없이 실행했을 때 박수 감지가 돌아갑니다.
"""

import argparse
import sys

from . import __version__


def _force_utf8_console() -> None:
    """콘솔 출력을 UTF-8로 강제한다.

    한글 Windows의 기본 콘솔 인코딩은 cp949라서 '—' 나 이모지(👏)를 출력하는 순간
    UnicodeEncodeError 로 프로그램이 죽는다. 로그를 한국어로 쓰는 이 앱에서는
    실제로 발생하는 문제라, 진입점에서 한 번 UTF-8로 바꿔둔다.
    errors='replace' 는 그래도 못 그리는 글자가 있을 때 죽는 대신 '?'로 대체하기 위함.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:  # 파이프로 연결된 경우 등 reconfigure가 없을 수 있다
            reconfigure(encoding="utf-8", errors="replace")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clap-launcher",
        description="박수 두 번(짝짝)으로 업무용 프로그램을 한 번에 실행합니다.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--list-devices", action="store_true",
        help="사용 가능한 마이크 목록을 보여줍니다.",
    )
    parser.add_argument(
        "--level", action="store_true",
        help="실시간 음량 미터를 켭니다. 마이크가 제대로 들리는지 확인용입니다.",
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
    _force_utf8_console()
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

    except AudioDeviceError as exc:
        # 마이크 문제는 사용자가 직접 고칠 수 있는 문제이므로,
        # 파이썬 traceback 대신 해결 방법이 담긴 메시지만 보여준다.
        print(f"\n❌ {exc}", file=sys.stderr)
        return 1

    print(f"Clapping Setup v{__version__}")
    print("아직 박수 감지 기능은 구현 전입니다 (진행 상황: docs/PLAN.md).")
    print("지금 해볼 수 있는 것:")
    print("  python -m clap_launcher --list-devices   마이크 목록 보기")
    print("  python -m clap_launcher --level          실시간 음량 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
