"""보정 로직 테스트.

보정은 "사용자의 마이크에서 나온 실제 박수"로 기준을 다시 잡는 기능이라,
잘못 만들면 **아무것도 감지 못 하는 설정**이 저장되어 프로그램이 먹통이 된다.
그래서 '보정한 기준으로 원래 박수가 다시 잡히는지'까지 확인한다.
"""

import numpy as np
import pytest

from clap_launcher.audio.features import EventFeatures, extract_event_features
from clap_launcher.config import DetectionConfig
from clap_launcher.detector.calibration import derive_config
from clap_launcher.detector.clap_detector import ClapDetector

from synth import SAMPLE_RATE, apply_limiter, build_stream, clap, frames_of, normalize

FIRST_SOUND_AT = 0.6


@pytest.fixture
def rng():
    return np.random.default_rng(20260808)


def clap_features(rng, count=5, limited=False):
    """박수를 여러 번 쳐서 특징값을 모은 것 — 실제 보정 과정을 흉내 낸다."""
    samples = []
    for _ in range(count):
        stream = build_stream([(0.02, normalize(clap(rng)))], 0.18, rng)
        if limited:
            stream = apply_limiter(stream)
        samples.append(extract_event_features(stream, SAMPLE_RATE))
    return samples


class TestDeriveConfig:
    def test_샘플이_없으면_거부한다(self):
        with pytest.raises(ValueError):
            derive_config([])

    def test_보정한_기준은_원래_박수를_받아들인다(self, rng):
        """⭐ 가장 중요한 성질: 보정하고 나서 내 박수가 안 잡히면 최악이다."""
        samples = clap_features(rng)
        config = derive_config(samples).config
        detector = ClapDetector(config, SAMPLE_RATE)

        for f in samples:
            assert detector._reject_reason(f) == "", \
                f"보정에 쓴 박수가 거부됨: {f.describe()}"

    def test_리미터_박수로_보정해도_그_박수를_받아들인다(self, rng):
        """⭐ 클리핑 가드가 걸린 마이크 환경에서의 보정."""
        samples = clap_features(rng, limited=True)
        config = derive_config(samples).config
        detector = ClapDetector(config, SAMPLE_RATE)

        for f in samples:
            assert detector._reject_reason(f) == "", \
                f"리미터 박수가 거부됨: {f.describe()}"

    def test_보정_뒤에도_기침은_계속_걸러진다(self, rng):
        """보정이 조건을 너무 헐겁게 만들어 오탐이 늘면 안 된다."""
        config = derive_config(clap_features(rng)).config
        detector = ClapDetector(config, SAMPLE_RATE)

        cough_like = EventFeatures(
            high_freq_ratio=0.15, flatness=0.14, zero_crossing_rate=0.21,
            harmonicity=0.91, decay_ms=120, crest_factor=4.1, peak=0.7,
        )
        assert detector._reject_reason(cough_like) != ""

    def test_관측값보다_여유를_둔다(self, rng):
        """5번 친 박수가 전부는 아니다. 경계선은 관측 범위보다 넓어야 한다."""
        samples = clap_features(rng)
        config = derive_config(samples).config
        assert config.min_high_freq_ratio < min(f.high_freq_ratio for f in samples)
        assert config.max_harmonicity > max(f.harmonicity for f in samples)
        assert config.max_decay_ms > max(f.decay_ms for f in samples)

    def test_샘플이_적으면_경고한다(self, rng):
        result = derive_config(clap_features(rng, count=2))
        assert any("샘플" in warning for warning in result.warnings)

    def test_눌린_소리면_리미터를_의심한다(self):
        """뾰족함(crest factor)이 낮으면 리미터가 걸려 있을 가능성이 높다."""
        squashed = [EventFeatures(0.9, 0.3, 0.6, 0.3, 25, crest_factor=2.5, peak=0.5)] * 5
        assert derive_config(squashed).limiter_suspected

    def test_말도_안_되는_값도_안전한_범위로_자른다(self):
        """이상한 샘플이 들어와도 '아무것도 감지 못 하는 설정'이 나오면 안 된다."""
        weird = [EventFeatures(0.0, 0.0, 0.0, 1.0, 9999, crest_factor=0.0, peak=0.0)] * 3
        config = derive_config(weird).config
        assert 0.0 <= config.min_high_freq_ratio <= 0.9
        assert 0.25 <= config.max_harmonicity <= 0.75
        assert config.max_decay_ms <= 150.0


class TestConfigSerialization:
    def test_저장했다_불러오면_같다(self):
        original = DetectionConfig(min_high_freq_ratio=0.71, max_decay_ms=44.0)
        assert DetectionConfig.from_dict(original.to_dict()) == original

    def test_빈_사전이면_기본값(self):
        assert DetectionConfig.from_dict({}) == DetectionConfig()

    def test_모르는_항목은_무시한다(self):
        """예전 버전이 저장한 항목 때문에 죽으면 안 된다."""
        config = DetectionConfig.from_dict({"max_decay_ms": 50.0, "옛날항목": 1})
        assert config.max_decay_ms == 50.0

    def test_보정용_설정은_박수를_통과시킨다(self, rng):
        """보정 중에는 조건이 느슨해야 어떤 마이크의 박수든 관찰할 수 있다."""
        detector = ClapDetector(DetectionConfig.for_calibration(), SAMPLE_RATE)
        for f in clap_features(rng, count=3):
            assert detector._reject_reason(f) == ""

    def test_보정용_설정도_명백한_쓰레기는_거른다(self):
        """조건을 완전히 열면 주변 소음이 샘플로 섞여 기준값이 망가진다(실제로 관찰됨)."""
        detector = ClapDetector(DetectionConfig.for_calibration(), SAMPLE_RATE)

        rumble = EventFeatures(0.02, 0.01, 0.06, 0.39, 120, crest_factor=3.0, peak=0.1)
        speech_like = EventFeatures(0.10, 0.05, 0.09, 0.95, 300, crest_factor=2.5, peak=0.5)
        assert detector._reject_reason(rumble) != ""
        assert detector._reject_reason(speech_like) != ""


class TestCalibratedDetection:
    def test_보정한_설정으로_실제_스트림에서_발동한다(self, rng):
        """특징값만이 아니라 전체 흐름(스트림 → 발동)까지 확인한다."""
        config = derive_config(clap_features(rng, limited=True)).config
        stream = apply_limiter(build_stream([
            (FIRST_SOUND_AT, normalize(clap(rng))),
            (FIRST_SOUND_AT + 0.3, normalize(clap(rng))),
        ], 2.0, rng))

        detector = ClapDetector(config, SAMPLE_RATE)
        triggered = any((event := detector.feed(f, t)) is not None and event.triggered
                        for f, t in frames_of(stream))
        assert triggered
