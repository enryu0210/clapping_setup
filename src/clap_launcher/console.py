"""콘솔 출력 인코딩 보정 + exe 에서 콘솔 되찾기.

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


_ATTACH_PARENT_PROCESS = -1      # AttachConsole 에 넘기면 '나를 실행한 콘솔'에 붙는다
_STD_FILENO = {"stdout": 1, "stderr": 2}


def _open_stream(target, closefd: bool):
    """UTF-8 로 쓰는 출력 스트림 하나를 연다. 못 열면 None."""
    try:
        return open(target, "w", encoding="utf-8", errors="replace",
                    buffering=1, closefd=closefd)
    except OSError:
        return None


def _attach_parent_console() -> bool:
    """나를 실행한 프로세스의 콘솔에 붙는다. 붙을 콘솔이 없으면 False."""
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.AttachConsole(_ATTACH_PARENT_PROCESS))
    except Exception:
        return False


def restore_console_output() -> bool:
    """exe 에서 사라진 stdout/stderr 를 되살린다.

    ⚠️ 왜 필요한가 (exe 로 만들고 나서야 드러나는 문제):
    exe 는 `--windowed` 로 묶어서 콘솔 창이 없다. 그래서 `sys.stdout` 이 아예 None 이고,
    `ClapDesk.exe --check-config` 같은 진단 명령을 실행해도 **아무것도 보이지 않는다.**
    정작 "박수를 쳐도 안 켜진다"를 풀 때 제일 필요한 기능인데, exe 로 배포하는 순간
    쓸 수 없게 되는 셈이다.

    두 가지 경우를 모두 살린다.
      1. 출력을 파일·파이프로 넘긴 경우 (`ClapDesk.exe --check-config > log.txt`)
         → 넘겨받은 핸들(fd 1·2)이 살아 있으므로 그걸 다시 연다
      2. 터미널에서 그냥 실행한 경우
         → 나를 실행한 콘솔에 붙어서(CONOUT$) 화면에 찍는다

    탐색기에서 더블클릭한 경우에는 둘 다 없으므로 조용히 넘어간다(정상 동작).

    Returns:
        하나라도 되살렸으면 True.
    """
    # 소스로 실행할 때는 이미 콘솔이 멀쩡하다. 괜히 건드리면 오히려 출력이 꼬인다.
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    if sys.stdout is not None and sys.stderr is not None:
        return False

    attached = _attach_parent_console()
    restored = False
    for name, fileno in _STD_FILENO.items():
        if getattr(sys, name, None) is not None:
            continue
        # closefd=False : 넘겨받은 핸들은 우리 것이 아니므로 닫으면 안 된다
        stream = _open_stream(fileno, closefd=False)
        if stream is None and attached:
            stream = _open_stream("CONOUT$", closefd=True)
        if stream is not None:
            setattr(sys, name, stream)
            restored = True
    return restored
