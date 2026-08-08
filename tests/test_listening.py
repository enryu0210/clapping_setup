"""'언제 듣는가' 로직 테스트.

화면을 실제로 잠갔다 푸는 것과 5분을 기다리는 것은 자동 테스트가 불가능하다.
그래서 그 두 가지를 **판단 로직만 떼어내** 값으로 검증할 수 있게 만들어뒀다.
여기가 틀리면 마이크가 엉뚱한 때 켜지거나, 켜야 할 때 안 켜진다.
"""

import pytest

from clap_launcher.listening import ListeningSession, StopReason, format_remaining
from clap_launcher.session_lock import LockWatcher, is_session_locked


class TestLockWatcher:
    def test_시작하자마자_켜지지_않는다(self):
        """⭐ 첫 관찰은 기준점을 잡는 용도다.

        이게 틀리면 프로그램을 켜자마자 마이크가 열린다. (잠금 해제 상태로 시작하므로)
        """
        watcher = LockWatcher()
        assert watcher.update(locked=False) is False

    def test_잠갔다_풀면_알려준다(self):
        watcher = LockWatcher()
        watcher.update(locked=False)          # 기준점
        assert watcher.update(locked=True) is False    # 잠김 — 아직 아님
        assert watcher.update(locked=True) is False    # 계속 잠김
        assert watcher.update(locked=False) is True    # 🔓 풀렸다!

    def test_한_번만_알려준다(self):
        """계속 풀려 있다고 매번 알리면 마이크가 계속 다시 켜진다."""
        watcher = LockWatcher()
        watcher.update(False)
        watcher.update(True)
        assert watcher.update(False) is True
        assert watcher.update(False) is False
        assert watcher.update(False) is False

    def test_여러_번_잠갔다_풀면_그때마다_알려준다(self):
        watcher = LockWatcher()
        watcher.update(False)
        for _ in range(3):
            watcher.update(True)
            assert watcher.update(False) is True

    def test_상태를_모를_때는_이전_상태를_유지한다(self):
        """⭐ 조회 실패(None)를 '풀렸다'로 읽으면 엉뚱할 때 마이크가 켜진다."""
        watcher = LockWatcher()
        watcher.update(False)
        watcher.update(True)              # 잠김
        assert watcher.update(None) is False     # 잠깐 조회 실패 — 아무 일도 없어야 한다
        assert watcher.update(None) is False
        assert watcher.update(False) is True     # 진짜로 풀렸을 때만 알린다

    def test_모르는_상태로_시작해도_죽지_않는다(self):
        watcher = LockWatcher()
        assert watcher.update(None) is False

    def test_초기화하면_다시_첫_관찰이_된다(self):
        watcher = LockWatcher()
        watcher.update(True)
        watcher.reset()
        assert watcher.update(False) is False    # 기준점이 없으니 알리지 않는다


class TestListeningSession:
    def test_처음에는_듣지_않는다(self):
        session = ListeningSession()
        assert not session.armed
        assert session.stop_reason is StopReason.NEVER_STARTED

    def test_켜면_제한_시간이_생긴다(self):
        session = ListeningSession()
        session.arm(now=100.0, timeout_min=5)
        assert session.armed
        assert session.remaining(100.0) == pytest.approx(300.0)
        assert session.remaining(250.0) == pytest.approx(150.0)

    def test_시간이_다_되면_만료된다(self):
        session = ListeningSession()
        session.arm(now=0.0, timeout_min=5)
        assert not session.is_expired(299.0)
        assert session.is_expired(300.0)
        assert session.is_expired(999.0)

    def test_남은_시간은_음수가_되지_않는다(self):
        session = ListeningSession()
        session.arm(now=0.0, timeout_min=1)
        assert session.remaining(9999.0) == 0.0

    @pytest.mark.parametrize("timeout", [0, -1, 0.0])
    def test_시간_제한_0이면_무제한(self, timeout):
        session = ListeningSession()
        session.arm(now=0.0, timeout_min=timeout)
        assert session.remaining(99999.0) is None
        assert not session.is_expired(99999.0)

    def test_멈추면_이유가_남는다(self):
        session = ListeningSession()
        session.arm(now=0.0, timeout_min=5)
        session.disarm(StopReason.TRIGGERED)
        assert not session.armed
        assert session.stop_reason is StopReason.TRIGGERED
        assert session.remaining(1.0) is None

    def test_멈춘_뒤에는_만료되지_않는다(self):
        """이미 멈췄는데 또 '시간 초과'로 처리되면 안내 문구가 뒤바뀐다."""
        session = ListeningSession()
        session.arm(now=0.0, timeout_min=1)
        session.disarm(StopReason.TRIGGERED)
        assert not session.is_expired(99999.0)


class TestFormatRemaining:
    @pytest.mark.parametrize("seconds,expected", [
        (300.0, "5:00"), (272.0, "4:32"), (59.9, "0:59"), (0.0, "0:00"), (None, ""),
    ])
    def test_표시_형식(self, seconds, expected):
        assert format_remaining(seconds) == expected


def test_현재_기기의_잠금_상태를_읽을_수_있다():
    """실제 Windows API가 동작하는지 확인한다.

    테스트가 도는 동안은 화면이 잠겨 있지 않으므로 False 여야 한다.
    (Windows가 아니면 None 이 정상)
    """
    import sys

    state = is_session_locked()
    if sys.platform == "win32":
        assert state is False, "테스트 중에는 화면이 잠겨 있지 않아야 한다"
    else:
        assert state is None
