"""[4] 등록된 프로그램들을 순서대로 실행한다.

핵심 원칙: **하나가 실패해도 멈추지 않는다.**
설정에 적힌 경로 하나가 오타여도 나머지 7개는 정상적으로 켜져야 한다.
실패는 모아뒀다가 마지막에 한 번에 알려준다.

⚠️ 여기서는 자식 프로그램을 기다리지 않는다(Popen 만 하고 wait 하지 않는다).
   VS Code 가 꺼질 때까지 기다렸다간 이 프로그램이 통째로 멈춘다.
"""

import os
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

from ..config import AppEntry


class LaunchError(Exception):
    """항목 하나를 실행하지 못했을 때. 메시지는 사용자에게 그대로 보여준다."""


@dataclass
class LaunchResult:
    """실행 결과 요약. 사용자에게 '뭐가 켜지고 뭐가 실패했는지' 알려주기 위한 것."""

    succeeded: list[str] = field(default_factory=list)              # 성공한 앱 이름
    failed: list[tuple[str, str]] = field(default_factory=list)     # (앱 이름, 실패 이유)
    skipped: int = 0                                                # enabled: false 로 건너뛴 개수

    @property
    def ok(self) -> bool:
        return not self.failed

    def summary(self) -> str:
        """예: '성공 6개 / 실패 1개 — Slack: 경로를 찾을 수 없습니다'

        실패한 것이 있으면 **이름과 이유를 반드시 함께** 보여준다.
        "1개 실패"만 알려주면 사용자는 무엇을 고쳐야 할지 알 수 없다.
        """
        if not self.succeeded and not self.failed:
            return "실행할 프로그램이 없습니다."

        parts = [f"성공 {len(self.succeeded)}개"]
        if self.failed:
            parts.append(f"실패 {len(self.failed)}개")
        if self.skipped:
            parts.append(f"꺼둔 항목 {self.skipped}개")
        text = " / ".join(parts)

        if self.failed:
            details = "  ·  ".join(f"{name}: {reason}" for name, reason in self.failed)
            text += f" — {details}"
        return text


# ── type 별 실행 방법 ─────────────────────────────────────────
# 각 함수는 성공하면 그냥 돌아오고, 실패하면 LaunchError 를 던진다.

def _detached_flags() -> int:
    """부모(이 프로그램)가 꺼져도 자식이 살아남게 하는 Windows 전용 옵션.

    이걸 안 주면 콘솔에서 실행했을 때 창을 닫는 순간 켜둔 프로그램들이 같이 죽는다.
    Windows 가 아니면 해당 상수가 없으므로 0(옵션 없음)이 된다.
    """
    return (getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


def launch_exe(entry: AppEntry) -> None:
    """설치된 프로그램을 실행한다."""
    target = Path(os.path.expandvars(entry.path)).expanduser()

    # 경로 검사를 먼저 하는 이유: subprocess 오류 메시지(WinError 2)보다
    # "경로를 찾을 수 없습니다: <경로>" 가 훨씬 고치기 쉽다.
    if not target.exists():
        raise LaunchError(f"경로를 찾을 수 없습니다: {target}")
    if target.is_dir():
        raise LaunchError(f"폴더 경로입니다. type 을 folder 로 바꿔주세요: {target}")

    try:
        subprocess.Popen(
            [str(target), *entry.args],
            cwd=str(target.parent),        # 프로그램이 옆 파일을 찾는 경우가 많다
            creationflags=_detached_flags(),
            close_fds=True,
        )
    except OSError as exc:
        raise LaunchError(f"실행하지 못했습니다: {exc}") from exc


def launch_url(entry: AppEntry) -> None:
    """기본 브라우저로 웹 주소를 연다."""
    url = entry.path
    # 'github.com' 처럼 http 를 빠뜨리면 브라우저가 파일 경로로 오해한다. 흔한 실수라 보정해 준다.
    if "://" not in url and not url.startswith("mailto:"):
        url = f"https://{url}"

    try:
        opened = webbrowser.open(url)
    except OSError as exc:
        raise LaunchError(f"브라우저를 열지 못했습니다: {exc}") from exc
    if not opened:
        raise LaunchError("기본 브라우저를 찾지 못했습니다.")


def launch_folder(entry: AppEntry) -> None:
    """탐색기로 폴더를 연다."""
    target = Path(os.path.expandvars(entry.path)).expanduser()
    if not target.is_dir():
        raise LaunchError(f"폴더를 찾을 수 없습니다: {target}")

    try:
        if hasattr(os, "startfile"):       # Windows
            os.startfile(str(target))      # noqa: S606 - 사용자가 직접 적은 경로다
        else:                              # 개발용 (macOS/Linux 에서 테스트할 때)
            subprocess.Popen(["xdg-open", str(target)])
    except OSError as exc:
        raise LaunchError(f"폴더를 열지 못했습니다: {exc}") from exc


def launch_store(entry: AppEntry) -> None:
    """Microsoft Store 앱을 연다.

    스토어 앱은 exe 경로가 없어서 일반 실행이 안 된다. Windows 가 제공하는
    'shell:AppsFolder\\<앱ID>' 라는 특수 주소를 탐색기에 넘겨야 한다.

    ⚠️ 앱 ID 가 틀려도 탐색기가 조용히 앱 목록 창만 띄우고 오류를 주지 않는다.
       즉 여기서 성공했다고 해서 앱이 반드시 켜진 것은 아니다. ID 확인은 docs/CONFIG.md 3장.
    """
    if sys.platform != "win32":
        raise LaunchError("스토어 앱(store)은 Windows 에서만 열 수 있습니다.")
    try:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{entry.path}"])
    except OSError as exc:
        raise LaunchError(f"스토어 앱을 열지 못했습니다: {exc}") from exc


DEFAULT_LAUNCHERS = {
    "exe": launch_exe,
    "url": launch_url,
    "folder": launch_folder,
    "store": launch_store,
}


class AppLauncher:
    """설정의 apps 목록을 실행한다. type 별로 여는 방식이 다르다.

      exe    : subprocess 로 실행파일 + 인자 실행
      url    : 기본 브라우저로 주소 열기
      folder : 탐색기로 폴더 열기
      store  : Microsoft Store 앱 (shell:AppsFolder 경유)

    ⚠️ launchers 와 sleep 을 밖에서 바꿔 끼울 수 있게 만든 이유:
       테스트할 때마다 진짜로 VS Code 8개가 켜지고 delay 만큼 진짜로 기다리면
       테스트를 돌릴 수가 없다. 가짜 실행기를 넣어 '무엇을 어떤 순서로 실행했는지'만 본다.
    """

    def __init__(self, launchers: dict | None = None, sleep=time.sleep) -> None:
        self._launchers = DEFAULT_LAUNCHERS if launchers is None else launchers
        self._sleep = sleep

    def launch_all(self, apps: list[AppEntry]) -> LaunchResult:
        """enabled 인 항목만, 목록 순서대로 실행하고 delay 만큼 쉬어간다."""
        targets = [app for app in apps if app.enabled]
        result = LaunchResult(skipped=len(apps) - len(targets))

        for order, entry in enumerate(targets):
            self._launch_one(entry, result)

            # 마지막 항목 뒤에는 기다릴 이유가 없다 (괜히 화면 복귀만 늦어진다)
            is_last = order == len(targets) - 1
            if entry.delay > 0 and not is_last:
                self._sleep(entry.delay)

        return result

    def _launch_one(self, entry: AppEntry, result: LaunchResult) -> None:
        """항목 하나를 실행하고 결과를 result 에 적는다. **여기서 예외가 새어 나가면 안 된다.**"""
        launcher = self._launchers.get(entry.type)
        if launcher is None:
            result.failed.append((entry.name, f"모르는 type 입니다: {entry.type}"))
            return

        try:
            launcher(entry)
        except LaunchError as exc:
            result.failed.append((entry.name, str(exc)))
        except Exception as exc:
            # 예상 못 한 오류 하나 때문에 나머지 프로그램이 안 켜지는 일은 없어야 한다.
            result.failed.append((entry.name, f"예상치 못한 오류: {exc}"))
        else:
            result.succeeded.append(entry.name)
