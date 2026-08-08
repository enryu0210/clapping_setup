"""박수 감지 로직 테스트 — 마이크 없이, 합성한 소리로 검증한다.

매번 손뼉을 쳐서 확인하면 개발이 불가능하다. 여기서 하는 일:
배경 잡음이 깔린 타임라인에 소리를 심고, 10ms 조각으로 잘라 감지기에 흘려 넣는다.

특히 **리미터(클리핑 가드)를 스트림 전체에 건 상태**로도 같은 테스트를 돌린다.
사용자의 마이크가 그런 환경이라, 여기가 깨지면 실전에서 안 된다.
"""

import numpy as np
import pytest

from clap_launcher.config import DetectionConfig
from clap_launcher.detector.clap_detector import ClapDetector

from synth import (   # tests 폴더가 sys.path에 들어가므로 그냥 이름으로 가져온다
    SAMPLE_RATE,
    apply_limiter,
    build_stream,
    clap,
    cough,
    door_slam,
    frames_of,
    keyboard,
    normalize,
    paper,
    speech,
)

FIRST_SOUND_AT = 0.6   # 감지기가 배경 소음을 파악할 시간을 준 뒤 첫 소리를 낸다


@pytest.fixture
def rng():
    """테스트가 매번 같은 결과를 내도록 씨앗을 고정한다."""
    return np.random.default_rng(20260808)


def run_detector(stream: np.ndarray, config: DetectionConfig | None = None):
    """스트림을 감지기에 흘려 넣고 (발동 여부, 모든 이벤트) 를 돌려준다."""
    detector = ClapDetector(config or DetectionConfig(), SAMPLE_RATE)
    events = []
    triggered = False
    for frame, now in frames_of(stream):
        event = detector.feed(frame, now)
        if event is not None:
            events.append(event)
            triggered = triggered or event.triggered
    return triggered, events


def two_sounds(rng, maker, gap_sec: float = 0.25, **kwargs):
    """같은 소리를 정해진 간격으로 두 번 낸 스트림을 만든다."""
    events = [
        (FIRST_SOUND_AT, normalize(maker(rng, **kwargs))),
        (FIRST_SOUND_AT + gap_sec, normalize(maker(rng, **kwargs))),
    ]
    return build_stream(events, duration_sec=FIRST_SOUND_AT + gap_sec + 1.0, rng=rng)


# ── 발동해야 하는 경우 ────────────────────────────────────

class TestShouldTrigger:
    def test_박수_두_번이면_발동한다(self, rng):
        triggered, events = run_detector(two_sounds(rng, clap, gap_sec=0.25))
        assert triggered, f"발동하지 않음. 감지된 이벤트: {[e.describe() for e in events]}"

    @pytest.mark.parametrize("gap", [0.18, 0.25, 0.4, 0.6, 0.75])
    def test_다양한_간격의_박수를_인식한다(self, rng, gap):
        """사람마다 박수 속도가 다르다. 허용 범위 안이면 모두 인식해야 한다."""
        triggered, _ = run_detector(two_sounds(rng, clap, gap_sec=gap))
        assert triggered, f"{gap}초 간격 박수를 놓침"

    def test_리미터가_걸려도_발동한다(self, rng):
        """⭐ 핵심 테스트: 클리핑 가드가 걸린 마이크 환경.

        리미터를 스트림 전체에 걸면 '펌핑'이 생겨 두 번째 박수가 작아진다.
        절대 음량으로 판단했다면 여기서 두 번째 박수를 놓쳤을 것이다.
        """
        stream = apply_limiter(two_sounds(rng, clap, gap_sec=0.25))
        triggered, events = run_detector(stream)
        assert triggered, f"리미터 환경에서 놓침. 이벤트: {[e.describe() for e in events]}"

    def test_리미터가_세게_걸려도_발동한다(self, rng):
        """더 가혹한 조건: 임계값을 낮추고 압축을 세게 걸었을 때."""
        stream = apply_limiter(two_sounds(rng, clap, gap_sec=0.3),
                               threshold_db=-30.0, makeup_db=20.0)
        triggered, events = run_detector(stream)
        assert triggered, f"강한 리미터에서 놓침. 이벤트: {[e.describe() for e in events]}"

    def test_박수가_작아도_지문으로_인식한다(self, rng):
        """멀리서 친 작은 박수. 크기가 아니라 소리의 성질로 판단하므로 잡혀야 한다."""
        events = [
            (FIRST_SOUND_AT, normalize(clap(rng), peak=0.08)),
            (FIRST_SOUND_AT + 0.25, normalize(clap(rng), peak=0.08)),
        ]
        triggered, _ = run_detector(build_stream(events, 2.0, rng))
        assert triggered


# ── 발동하면 안 되는 경우 (오탐 방지) ─────────────────────

class TestShouldNotTrigger:
    def test_기침_두_번에는_반응하지_않는다(self, rng):
        """⭐ 사용자가 가장 걱정한 경우. 음정(하모니시티)으로 걸러야 한다."""
        triggered, events = run_detector(two_sounds(rng, cough))
        assert not triggered
        assert any("음정" in e.reject_reason for e in events), \
            f"음정 때문에 걸러져야 하는데 다른 이유로 걸러짐: {[e.describe() for e in events]}"

    def test_말소리에는_반응하지_않는다(self, rng):
        triggered, _ = run_detector(two_sounds(rng, speech))
        assert not triggered

    def test_문_닫는_소리에는_반응하지_않는다(self, rng):
        """저음 덩어리라 고음 비율에서 걸러진다."""
        triggered, events = run_detector(two_sounds(rng, door_slam))
        assert not triggered
        assert any("고음" in e.reject_reason for e in events), \
            f"고음 부족으로 걸러져야 함: {[e.describe() for e in events]}"

    def test_종이_구기는_소리에는_반응하지_않는다(self, rng):
        """⭐ 지문(고음·평탄도·ZCR)이 박수와 거의 같다. **길이로만** 구분된다."""
        triggered, events = run_detector(two_sounds(rng, paper))
        assert not triggered
        assert any("길게" in e.reject_reason for e in events), \
            f"길이로 걸러져야 함: {[e.describe() for e in events]}"

    def test_기침_뒤_박수_한_번은_발동하지_않는다(self, rng):
        """섞여 있어도 기침은 박수로 세면 안 된다."""
        events = [
            (FIRST_SOUND_AT, normalize(cough(rng))),
            (FIRST_SOUND_AT + 0.3, normalize(clap(rng))),
        ]
        triggered, _ = run_detector(build_stream(events, 2.0, rng))
        assert not triggered

    def test_박수_한_번만으로는_발동하지_않는다(self, rng):
        stream = build_stream([(FIRST_SOUND_AT, normalize(clap(rng)))], 2.0, rng)
        triggered, events = run_detector(stream)
        assert not triggered
        assert any(e.is_clap for e in events), "박수 자체는 인식했어야 한다"

    def test_너무_느린_박수는_발동하지_않는다(self, rng):
        """1.5초 간격. 우연히 두 번 난 소리일 가능성이 크다."""
        triggered, _ = run_detector(two_sounds(rng, clap, gap_sec=1.5))
        assert not triggered

    def test_너무_빠른_박수는_발동하지_않는다(self, rng):
        """50ms 간격은 한 번의 박수가 울린 여운일 가능성이 높다."""
        triggered, _ = run_detector(two_sounds(rng, clap, gap_sec=0.05))
        assert not triggered

    def test_조용하면_아무것도_감지하지_않는다(self, rng):
        """배경 잡음만 있을 때 헛감지가 없어야 한다."""
        _, events = run_detector(build_stream([], 3.0, rng))
        assert events == []

    def test_키보드_소리로는_발동하지_않는다(self, rng):
        """타이핑하듯 여러 번 두드려도 반응하면 안 된다."""
        strokes = [(FIRST_SOUND_AT + i * 0.13, normalize(keyboard(rng), peak=0.25))
                   for i in range(6)]
        triggered, _ = run_detector(build_stream(strokes, 2.5, rng))
        assert not triggered


# ── 쿨다운 ────────────────────────────────────────────────

class TestCooldown:
    def test_발동_직후_박수는_다시_발동하지_않는다(self, rng):
        """프로그램이 켜지는 동안 또 발동하면 안 된다."""
        events = [(FIRST_SOUND_AT + offset, normalize(clap(rng)))
                  for offset in (0.0, 0.25, 1.0, 1.25)]
        stream = build_stream(events, 3.5, rng)
        _, detected = run_detector(stream, DetectionConfig(cooldown_sec=5.0))
        assert sum(1 for e in detected if e.triggered) == 1, "한 번만 발동해야 한다"

    def test_쿨다운이_끝나면_다시_발동한다(self, rng):
        events = [(FIRST_SOUND_AT + offset, normalize(clap(rng)))
                  for offset in (0.0, 0.25, 1.6, 1.85)]
        stream = build_stream(events, 4.0, rng)
        _, detected = run_detector(stream, DetectionConfig(cooldown_sec=0.5))
        assert sum(1 for e in detected if e.triggered) == 2
