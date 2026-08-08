"""진입점 — `python -m clap_launcher` 로 실행됩니다.

구현이 끝나면 이 파일이 하는 일:
  1. config.load_config() 로 설정 읽기
  2. AudioListener 로 마이크 열기
  3. 들어오는 조각마다 ClapDetector 에 넘기기
  4. 감지되면 AppLauncher 로 프로그램 실행

지금은 뼈대만 있어서 안내 메시지만 출력합니다.
"""

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


def main() -> int:
    """실행 결과를 종료 코드로 반환한다 (0=정상). TODO: M4에서 실제 루프 구현."""
    _force_utf8_console()
    print(f"Clapping Setup v{__version__} — 아직 기획 단계입니다.")
    print("개발 계획은 docs/PLAN.md, 구조 설계는 docs/ARCHITECTURE.md 를 보세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
