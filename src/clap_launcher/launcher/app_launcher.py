"""[4] 등록된 프로그램들을 순서대로 실행한다.

핵심 원칙: **하나가 실패해도 멈추지 않는다.**
설정에 적힌 경로 하나가 오타여도 나머지 7개는 정상적으로 켜져야 한다.
실패는 모아뒀다가 마지막에 한 번에 알려준다.

TODO(M4): 실제 실행 구현.
"""

from dataclasses import dataclass


@dataclass
class LaunchResult:
    """실행 결과 요약. 사용자에게 '뭐가 켜지고 뭐가 실패했는지' 알려주기 위한 것."""

    succeeded: list[str]              # 성공한 앱 이름
    failed: list[tuple[str, str]]     # (앱 이름, 실패 이유)

    def summary(self) -> str:
        """예: '성공 6개 / 실패 1개 — Slack: 경로를 찾을 수 없음'"""
        raise NotImplementedError("TODO(M4)")


class AppLauncher:
    """설정의 apps 목록을 실행한다. type 별로 여는 방식이 다르다.

      exe    : subprocess 로 실행파일 + 인자 실행
      url    : 기본 브라우저로 주소 열기
      folder : 탐색기로 폴더 열기
      store  : Microsoft Store 앱 (shell:AppsFolder 경유)
    """

    def launch_all(self, apps) -> LaunchResult:
        """enabled 인 항목만, 목록 순서대로 실행하고 delay 만큼 쉬어간다."""
        raise NotImplementedError("TODO(M4): type 별 실행 분기 + 예외 수집")
