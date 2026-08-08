"""화면이 "새 이벤트"를 골라내는 계산 테스트.

⚠️ 이 테스트가 존재하는 이유 (실제로 겪은 버그):
모니터는 최근 이벤트 12개만 들고 있는데, 화면은 "어디까지 봤는지"를 **목록 길이**로
세고 있었다. 이벤트가 12개를 넘는 순간 길이가 12에서 멈추므로, 화면은 그 뒤로
"새 이벤트가 없다"고 착각하고 **로그가 조용히 멈췄다.**

몇 초 동안은 멀쩡히 동작하다가 멈추는 종류라 눈으로는 원인을 알기 어렵다.
누적 개수 기준으로 바꾼 뒤, 버퍼가 넘치는 상황을 여기서 못 박아둔다.
"""

import pytest

from clap_launcher.ui.audio_monitor import RECENT_EVENT_LIMIT, take_new_events


def fake_events(count: int) -> tuple[str, ...]:
    """이벤트 대신 알아보기 쉬운 문자열을 쓴다. 여기서 검증하는 건 개수 계산뿐이다."""
    return tuple(f"e{i}" for i in range(count))


class TestTakeNewEvents:
    def test_처음에는_모두_새것(self):
        events = fake_events(3)
        assert take_new_events(events, total_count=3, seen_count=0) == (events, 0)

    def test_이미_다_봤으면_비어_있다(self):
        events = fake_events(3)
        assert take_new_events(events, total_count=3, seen_count=3) == ((), 0)

    def test_마지막_하나만_새것(self):
        events = fake_events(3)
        new, dropped = take_new_events(events, total_count=3, seen_count=2)
        assert new == ("e2",) and dropped == 0

    def test_버퍼가_가득_차도_계속_새것을_돌려준다(self):
        """⭐ 로그가 멈췄던 바로 그 상황.

        이벤트가 100개 나왔고 화면은 99개까지 봤다. 버퍼에는 최근 12개만 남아 있다.
        목록 길이로 셌다면 여기서 빈 결과가 나와 로그가 멈춘다.
        """
        buffer = fake_events(RECENT_EVENT_LIMIT)
        new, dropped = take_new_events(buffer, total_count=100, seen_count=99)
        assert len(new) == 1, "버퍼가 찼다고 새 이벤트를 놓치면 안 된다"
        assert dropped == 0

    def test_한참_밀리면_놓친_개수를_알려준다(self):
        """화면 갱신이 크게 밀리면 버퍼에서 사라진 이벤트가 생긴다. 조용히 삼키지 않는다."""
        buffer = fake_events(RECENT_EVENT_LIMIT)
        new, dropped = take_new_events(buffer, total_count=100, seen_count=80)
        assert len(new) == RECENT_EVENT_LIMIT
        assert dropped == 20 - RECENT_EVENT_LIMIT

    def test_다시_시작해서_개수가_줄어도_죽지_않는다(self):
        """마이크를 바꾸면 누적 개수가 0으로 초기화된다. 음수 인덱스가 되면 안 된다."""
        assert take_new_events(fake_events(2), total_count=1, seen_count=50) == ((), 0)

    def test_이벤트가_없으면_비어_있다(self):
        assert take_new_events((), total_count=0, seen_count=0) == ((), 0)

    @pytest.mark.parametrize("total", range(1, 40))
    def test_한_개씩_계속_흘려보내도_빠짐없이_전달된다(self, total):
        """가장 중요한 성질: 오랫동안 돌려도 하나도 안 빠지고 이어져야 한다."""
        seen = 0
        delivered = 0
        for count in range(1, total + 1):
            buffer = fake_events(count)[-RECENT_EVENT_LIMIT:]
            new, dropped = take_new_events(buffer, total_count=count, seen_count=seen)
            delivered += len(new) + dropped
            seen = count
        assert delivered == total
