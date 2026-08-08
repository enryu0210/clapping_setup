"""Windows 화면 잠금 상태 읽기.

왜 필요한가:
박수 감지를 하루 종일 켜두면, 아무리 정확해도 오탐이 언젠가는 난다.
8시간 동안 듣는 것과 잠금 해제 직후 몇 분만 듣는 것은 위험 노출이 100배 이상 차이 난다.
게다가 "자리에 돌아와 컴퓨터를 켜는 순간"이야말로 업무 프로그램을 띄우고 싶은 바로 그 순간이다.

그래서 화면 잠금이 풀리는 순간을 감지해 그때만 마이크를 연다.

구현 방식:
Windows 세션 알림(WM_WTSSESSION_CHANGE)을 제대로 받으려면 창 핸들과 메시지 루프가 필요해
Tkinter 와 엮기가 까다롭다. 잠금 해제는 1~2초 늦게 알아도 아무 문제가 없으므로
**주기적으로 상태를 물어보는(polling) 방식**을 택했다. 훨씬 단순하고 의존성도 없다.
"""

import ctypes
import sys
from ctypes import wintypes

# WTSQuerySessionInformation 에 넘기는 값들
_WTS_CURRENT_SERVER_HANDLE = None
_WTS_CURRENT_SESSION = -1
_WTS_SESSION_INFO_EX = 25
_WTS_SESSIONSTATE_LOCK = 0
_WTS_SESSIONSTATE_UNLOCK = 1

# OpenInputDesktop 에 넘기는 접근 권한
_DESKTOP_SWITCHDESKTOP = 0x0100


def _query_via_wts() -> bool | None:
    """WTSQuerySessionInformation 으로 잠금 여부를 읽는다.

    가장 정확한 방법이라 먼저 시도한다.
    WTSINFOEX_LEVEL1 구조체에서 SessionFlags 만 필요하므로, 구조체를 전부 정의하는 대신
    바이트 위치로 꺼낸다. (Level 4바이트 + 정렬 4바이트, SessionId 4, SessionState 4, 그다음 SessionFlags)
    """
    try:
        wts = ctypes.WinDLL("wtsapi32")
    except OSError:
        return None

    buffer = ctypes.c_void_p()
    size = wintypes.DWORD()
    ok = wts.WTSQuerySessionInformationW(
        _WTS_CURRENT_SERVER_HANDLE, _WTS_CURRENT_SESSION, _WTS_SESSION_INFO_EX,
        ctypes.byref(buffer), ctypes.byref(size),
    )
    if not ok or size.value < 20:
        return None

    try:
        raw = ctypes.string_at(buffer, size.value)
        flags = int.from_bytes(raw[16:20], "little", signed=True)
    finally:
        wts.WTSFreeMemory(buffer)

    if flags == _WTS_SESSIONSTATE_LOCK:
        return True
    if flags == _WTS_SESSIONSTATE_UNLOCK:
        return False
    return None      # 문서에 없는 값이면 함부로 단정하지 않는다


def _query_via_desktop() -> bool | None:
    """입력 데스크톱을 열어볼 수 있는지로 판단한다 (대체 수단).

    잠겨 있으면 다른 데스크톱(잠금 화면)이 입력을 가지고 있어서 열기에 실패한다.
    ⚠️ UAC 확인 창 같은 보안 데스크톱이 떠 있을 때도 실패하므로 100% 정확하지는 않다.
       그래서 WTS 가 실패했을 때만 쓴다.
    """
    try:
        user32 = ctypes.WinDLL("user32")
    except OSError:
        return None

    handle = user32.OpenInputDesktop(0, False, _DESKTOP_SWITCHDESKTOP)
    if handle:
        user32.CloseDesktop(handle)
        return False
    return True


def is_session_locked() -> bool | None:
    """화면이 잠겨 있으면 True, 아니면 False.

    Returns:
        판단할 수 없으면 None. (Windows 가 아니거나 API 호출이 실패한 경우)
        **None 을 False 로 취급하면 안 된다.** '잠금 해제됨'으로 잘못 읽혀
        엉뚱한 순간에 마이크가 켜진다.
    """
    if sys.platform != "win32":
        return None
    return _query_via_wts() if _query_via_wts() is not None else _query_via_desktop()


class LockWatcher:
    """잠금 상태를 지켜보다가 '방금 풀렸다'를 알려준다.

    상태 판단을 순수한 계산으로 떼어놨다(update 가 값을 인자로 받는다).
    실제로 화면을 잠갔다 푸는 건 자동 테스트가 불가능하므로, 이 부분만이라도
    테스트로 검증할 수 있어야 한다.
    """

    def __init__(self) -> None:
        self._was_locked: bool | None = None

    def update(self, locked: bool | None) -> bool:
        """현재 잠금 상태를 넣는다. **방금 잠금이 풀린 순간에만** True 를 반환한다.

        - 프로그램 시작 직후에는 절대 True 를 반환하지 않는다.
          (첫 관찰은 기준점을 잡는 용도다. 안 그러면 켜자마자 마이크가 켜진다)
        - 알 수 없음(None)이 들어오면 이전 상태를 그대로 유지한다.
          잠깐 조회에 실패했다고 '풀렸다'고 단정하면 안 된다.
        """
        if locked is None:
            return False

        unlocked_just_now = self._was_locked is True and locked is False
        self._was_locked = locked
        return unlocked_just_now

    def reset(self) -> None:
        """기준점을 지운다. 다음 관찰이 다시 첫 관찰이 된다."""
        self._was_locked = None
