"""모든 테스트가 함께 쓰는 준비물.

⚠️ 여기에 Tk 창 하나를 두는 이유 (실제로 겪은 문제):
테스트 파일마다 각자 `tk.Tk()` 를 만들면, **두 번째로 만드는 창부터 실패한다.**
한 프로세스 안에서 Tk 인터프리터를 만들었다 없앴다 반복하면 안정적으로 동작하지 않는다.

더 나쁜 건, 실패가 "화면이 없는 환경"으로 오인돼 테스트가 조용히 건너뛰어진다는 점이다.
UI 테스트 30개가 통과한 척 사라지는 상황이 실제로 있었다.
그래서 창은 **세션 전체에서 하나만** 만들고 모두가 나눠 쓴다.
"""

import tkinter as tk

import pytest


@pytest.fixture(scope="session")
def root():
    """숨긴 Tk 창 하나. 위젯을 만들려면 창이 있어야 한다.

    화면이 정말 없는 환경(CI 등)에서는 건너뛴다.
    """
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip("화면이 없는 환경이라 Tk를 띄울 수 없습니다")
    window.withdraw()
    yield window
    window.destroy()
