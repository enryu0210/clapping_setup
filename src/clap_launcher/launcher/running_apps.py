"""지금 실행 중인 프로그램 목록 읽기 — 같은 프로그램을 두 번 켜지 않기 위해.

왜 필요한가:
아침에 박수를 쳐서 8개를 켰는데, 점심 먹고 와서 또 박수를 치면 VS Code 창이 하나 더 뜬다.
이미 켜져 있는 것은 건너뛰는 게 자연스럽다.

왜 psutil 을 안 쓰는가:
프로세스 목록 하나 보려고 의존성을 늘리면 exe 크기와 패키징 위험이 함께 늘어난다.
Windows API 를 ctypes 로 직접 부르면 표준 라이브러리만으로 끝난다.
(session_lock.py 에서 이미 같은 방식을 쓰고 있다)

⚠️ 한계: 실행파일 **이름**으로만 비교한다. 경로가 다른 동명이인(예: 서로 다른 폴더의
   `python.exe`)은 같은 것으로 본다. 프로세스의 전체 경로를 읽으려면 권한이 더 필요하고
   실패하는 경우도 많아서, 이 정도의 단순함이 낫다고 판단했다.
"""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

# CreateToolhelp32Snapshot 에 넘기는 값
_TH32CS_SNAPPROCESS = 0x00000002
_INVALID_HANDLE_VALUE = -1
_MAX_PATH = 260


class _PROCESSENTRY32W(ctypes.Structure):
    """프로세스 하나의 정보. Windows 가 정해둔 구조체라 순서를 바꾸면 안 된다."""

    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * _MAX_PATH),
    ]


def list_running_processes() -> set[str]:
    """지금 돌고 있는 프로세스의 실행파일 이름들 (전부 소문자).

    Returns:
        예: {"chrome.exe", "code.exe", "explorer.exe"}
        Windows 가 아니거나 조회에 실패하면 **빈 집합**. 그러면 '아무것도 안 켜져 있다'로
        읽혀 평소처럼 전부 실행된다 — 조회 실패 때문에 프로그램이 안 켜지는 것보다 낫다.
    """
    if sys.platform != "win32":
        return set()

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:
        return set()

    snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snapshot == _INVALID_HANDLE_VALUE:
        return set()

    names: set[str] = set()
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return set()
        while True:
            names.add(entry.szExeFile.lower())
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break      # 목록 끝
    finally:
        kernel32.CloseHandle(snapshot)
    return names


def executable_name(path: str) -> str:
    """설정에 적힌 경로에서 실행파일 이름만 소문자로 뽑는다.

    예: "C:/Program Files/Microsoft VS Code/Code.exe" → "code.exe"
    """
    return Path(path.strip().replace("\\", "/")).name.lower()


def is_already_running(path: str, running: set[str]) -> bool:
    """이 경로의 프로그램이 이미 돌고 있는가.

    화면·OS와 상관없는 순수한 비교라 테스트하기 쉽다.
    (실제 프로세스 목록을 읽는 부분은 위 list_running_processes 가 맡는다)
    """
    name = executable_name(path)
    return bool(name) and name in running
