"""언제 마이크를 열고 언제 닫을지 결정한다.

설계가 바뀐 배경:
처음에는 프로그램이 켜져 있는 내내 마이크를 열어뒀다. 그런데 박수 감지를 아무리
정교하게 만들어도 **하루 8시간을 듣고 있으면 오탐은 언젠가 난다.** 확률 싸움에서 진다.

그래서 "얼마나 정확하게 듣느냐"가 아니라 **"언제 듣느냐"** 를 바꿨다.

  · 화면 잠금이 풀린 직후 몇 분  ← 자리에 돌아와 프로그램을 켜고 싶은 바로 그 순간
  · 사용자가 직접 켰을 때
  이 외에는 마이크를 아예 닫아둔다.

듣는 시간이 8시간에서 5분으로 줄면 오탐 확률도 그만큼 줄어든다.
덤으로 평소에는 마이크를 아예 잡지 않으므로 화상회의와 충돌하지도, 프라이버시 걱정도 없다.
"""

from dataclasses import dataclass
from enum import Enum, auto


class StopReason(Enum):
    """왜 듣기를 멈췄는가. 화면에 그대로 설명해 주기 위한 값."""

    NEVER_STARTED = auto()   # 아직 한 번도 시작 안 함
    TRIGGERED = auto()       # 박수를 감지해서 할 일을 마쳤다
    TIMED_OUT = auto()       # 정해진 시간 동안 박수가 없었다
    MANUAL = auto()          # 사용자가 직접 멈췄다


@dataclass
class ListeningSession:
    """'지금 듣고 있는가'와 '언제까지 들을 것인가'를 관리한다.

    ⚠️ 시간을 내부에서 읽지 않고 인자로 받는다.
       그래야 "5분 뒤 자동 종료"를 5분 기다리지 않고 테스트할 수 있다.
    """

    armed: bool = False
    deadline: float | None = None          # 이 시각이 지나면 자동으로 멈춘다 (None이면 무제한)
    stop_reason: StopReason = StopReason.NEVER_STARTED

    def arm(self, now: float, timeout_min: float) -> None:
        """듣기 시작. timeout_min 이 0 이하면 시간 제한 없이 계속 듣는다."""
        self.armed = True
        self.deadline = now + timeout_min * 60 if timeout_min > 0 else None

    def disarm(self, reason: StopReason) -> None:
        """듣기 중지. 이유를 남겨 화면에서 설명할 수 있게 한다."""
        self.armed = False
        self.deadline = None
        self.stop_reason = reason

    def remaining(self, now: float) -> float | None:
        """남은 시간(초). 무제한이거나 듣고 있지 않으면 None."""
        if not self.armed or self.deadline is None:
            return None
        return max(0.0, self.deadline - now)

    def is_expired(self, now: float) -> bool:
        """시간 제한이 다 됐는가."""
        return self.armed and self.deadline is not None and now >= self.deadline


def format_remaining(seconds: float | None) -> str:
    """남은 시간을 '4:32' 형태로. 무제한이면 빈 문자열."""
    if seconds is None:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"
