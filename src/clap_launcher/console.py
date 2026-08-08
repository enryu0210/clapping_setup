"""콘솔 출력 인코딩 보정.

왜 별도 파일인가: 이 처리가 필요한 곳이 두 군데다(콘솔 실행 경로와 GUI 실행 경로).
GUI라도 오류 메시지는 콘솔로 나가고, 개발 중에는 창을 띄운 채 콘솔 로그를 본다.
한쪽에만 넣어두면 다른 쪽에서 그대로 터진다. (실제로 그렇게 한 번 터졌다)
"""

import sys


def force_utf8_console() -> None:
    """콘솔 출력을 UTF-8로 강제한다.

    한글 Windows의 기본 콘솔 인코딩은 cp949라서 '—' 나 이모지(👏, ⏳)를 출력하는 순간
    UnicodeEncodeError 로 프로그램이 죽는다. 로그와 안내 문구를 한국어로 쓰는 이 앱에서는
    실제로 발생하는 문제라, 시작할 때 한 번 UTF-8로 바꿔둔다.
    errors='replace' 는 그래도 못 그리는 글자가 있을 때 죽는 대신 '?'로 대체하기 위함.
    """
    for stream in (sys.stdout, sys.stderr):
        # 파이프로 연결됐거나(exe로 패키징하면 stdout이 아예 없을 수도 있다)
        # 이미 닫힌 스트림이면 reconfigure 가 없다.
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass   # 인코딩을 못 바꿔도 프로그램이 죽을 이유는 없다
