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

from synth import (
    SAMPLE_RATE,
    apply_limiter,
    build_stream,
    clap,
    frames_of,
    keyboard,
    normalize,
)

FIRST_SOUND_AT = 0.6


@pytest.fixture
def rng():
    return np.random.default_rng(20260808)


def features_of(rng, maker, count=5, limited=False, peak=0.7):
    """소리를 여러 번 내서 특징값을 모은 것 — 실제 보정 과정을 흉내 낸다."""
    samples = []
    for _ in range(count):
        stream = build_stream([(0.02, normalize(maker(rng), peak))], 0.18, rng)
        if limited:
            stream = apply_limiter(stream)
        samples.append(extract_event_features(stream, SAMPLE_RATE))
    return samples


def clap_features(rng, count=5, limited=False):
    return features_of(rng, clap, count, limited)


def ringing_key_click() -> EventFeatures:
    """기계식 키보드의 '딸깍 + 여운' 소리.

    짧은 딸깍은 길이 하한으로 걸러지지만, 스위치가 울리는 키보드는 길이가
    박수와 비슷해서(22ms) 길이로는 못 거른다. 대신 백색잡음에 가까워 평탄도가 높다.
    잡음 샘플로 알려줘야만 막을 수 있는 종류의 소리다.
    """
    return EventFeatures(
        high_freq_ratio=0.70, flatness=0.60, zero_crossing_rate=0.50,
        harmonicity=0.20, decay_ms=22.0, crest_factor=9.0, peak=0.3,
    )


def dark_mic_claps(rng, count=5):
    """고음을 덜 잡는 마이크로 친 박수를 흉내 낸다.

    실제 마이크는 합성음만큼 밝지 않다. 이 상황에서 박수만 보고 보정하면
    경계선이 너무 내려가 키보드까지 들어오는 문제가 실제로 발생했다.
    """
    from dataclasses import replace
    return [replace(f, high_freq_ratio=f.high_freq_ratio * 0.6, flatness=f.flatness * 1.5)
            for f in clap_features(rng, count)]


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

    def test_잡음_없이_보정하면_경고한다(self, rng):
        """2단계를 건너뛰면 키보드가 뚫릴 수 있다는 걸 알려줘야 한다."""
        result = derive_config(clap_features(rng))
        assert any("잡음 수집을 건너뛰" in warning for warning in result.warnings)

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


class TestNoiseSamples:
    """⭐ 잡음 샘플(2단계)이 있어야 키보드가 막힌다 — 실제로 뚫렸던 시나리오."""

    def test_울리는_키보드는_박수만_보고_보정하면_뚫린다(self, rng):
        """⭐ 2단계가 필요한 이유를 못 박아두는 테스트.

        기계식 키보드처럼 '딸깍' 뒤에 여운이 남는 소리는 길이가 박수와 비슷해서
        길이 조건으로 못 거른다. 박수만 보고 정한 경계선 안에 그대로 들어온다.
        아래 테스트(잡음까지 주는 경우)와 짝을 이룬다.
        """
        claps = dark_mic_claps(rng)
        detector = ClapDetector(derive_config(claps).config, SAMPLE_RATE)
        assert detector._reject_reason(ringing_key_click()) == "", \
            "이 테스트의 전제(박수만 보면 뚫린다)가 깨졌다면 확인 필요"

    def test_울리는_키보드도_잡음으로_알려주면_막힌다(self, rng):
        """같은 소리라도 '이건 박수 아님'이라고 알려주면 경계선이 그 사이로 옮겨간다."""
        claps = dark_mic_claps(rng)
        click = ringing_key_click()

        detector = ClapDetector(derive_config(claps, [click]).config, SAMPLE_RATE)
        assert detector._reject_reason(click) != "", "잡음으로 줬는데도 통과함"
        for f in claps:
            assert detector._reject_reason(f) == "", "잡음을 막느라 박수까지 막으면 안 된다"

    def test_짧은_딸깍은_길이만으로도_막힌다(self, rng):
        """여운 없는 멤브레인 키보드는 길이 하한만으로 걸러진다 (잡음 샘플 없이도)."""
        claps = dark_mic_claps(rng)
        keys = features_of(rng, keyboard, peak=0.3)

        detector = ClapDetector(derive_config(claps).config, SAMPLE_RATE)
        leaked = [f for f in keys if detector._reject_reason(f) == ""]
        assert not leaked, f"짧은 키보드가 통과: {[x.describe() for x in leaked]}"

    def test_잡음을_막으면서_박수는_계속_받아들인다(self, rng):
        """가장 중요한 성질: 잡음을 막느라 내 박수까지 막으면 아무 의미가 없다."""
        claps = dark_mic_claps(rng)
        keys = features_of(rng, keyboard, peak=0.3)

        detector = ClapDetector(derive_config(claps, keys).config, SAMPLE_RATE)
        for f in claps:
            assert detector._reject_reason(f) == "", f"보정에 쓴 박수가 거부됨: {f.describe()}"

    def test_얼마나_막았는지_알려준다(self, rng):
        result = derive_config(dark_mic_claps(rng), features_of(rng, keyboard, peak=0.3))
        assert result.noise_count == 5
        assert result.noise_blocked_ratio == 1.0

    def test_잡음이_바짝_붙어도_박수_주변에_여유를_남긴다(self, rng):
        """⭐ 잡음을 막으려다 박수 창을 너무 좁게 만들면 안 된다.

        보정에 쓴 5번이 그 사람의 모든 박수는 아니다. 관측값에 딱 붙여 경계를 그으면
        조금만 다르게 친 박수가 바로 탈락한다. (실제로 '길이 24~30ms' 같은
        지나치게 좁은 창이 만들어지는 것을 확인해서 넣은 안전장치)
        """
        # 모든 박수의 길이가 26ms로 똑같고, 잡음이 바로 옆(24ms, 28ms)에 있는 극단적 상황
        claps = [EventFeatures(0.7, 0.3, 0.6, 0.3, 26.0, 8.0, 0.6)] * 5
        near_noise = [
            EventFeatures(0.7, 0.3, 0.6, 0.3, 24.0, 8.0, 0.3),
            EventFeatures(0.7, 0.3, 0.6, 0.3, 28.0, 8.0, 0.3),
        ]
        config = derive_config(claps, near_noise).config

        assert config.min_decay_ms <= 26.0 * 0.85, "하한이 박수에 너무 바짝 붙었다"
        assert config.max_decay_ms >= 26.0 * 1.18, "상한이 박수에 너무 바짝 붙었다"

    def test_길이가_들쭉날쭉한_박수도_모두_받아들인다(self, rng):
        """사람이 매번 똑같이 치지는 않는다. 보정 후에도 폭이 살아 있어야 한다."""
        claps = [EventFeatures(0.7, 0.3, 0.6, 0.3, decay, 8.0, 0.6)
                 for decay in (18.0, 22.0, 26.0, 31.0, 38.0)]
        detector = ClapDetector(derive_config(claps).config, SAMPLE_RATE)
        for f in claps:
            assert detector._reject_reason(f) == "", f"보정에 쓴 박수가 거부됨: {f.describe()}"

    def test_구분되지_않는_잡음이_있으면_알려준다(self, rng):
        """잡음이 박수와 물리적으로 같으면 막을 수 없다. 조용히 넘어가면 안 된다."""
        claps = clap_features(rng)
        result = derive_config(claps, claps)     # 잡음이 박수와 완전히 동일한 극단적 경우
        assert result.noise_blocked_ratio < 1.0
        assert any("구분되지 않" in warning for warning in result.warnings)


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
