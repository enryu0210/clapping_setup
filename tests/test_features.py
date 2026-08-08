"""음량 계산 테스트 — 마이크 없이 가짜 파형으로 검증한다.

숫자를 눈으로 보고 "대충 맞는 것 같다"고 넘어가면, 나중에 감지가 안 될 때
계산이 틀린 건지 감지 로직이 틀린 건지 알 수 없다. 여기서 계산을 못 박아둔다.
"""

import math

import numpy as np
import pytest

from clap_launcher.audio.features import SILENCE_DBFS, compute_rms, rms_to_dbfs


def make_sine(freq_hz: float, sample_rate: int = 16000, duration: float = 0.1,
              amplitude: float = 1.0) -> np.ndarray:
    """테스트용 사인파를 만든다."""
    t = np.arange(int(sample_rate * duration)) / sample_rate
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


class TestComputeRms:
    def test_무음은_0(self):
        assert compute_rms(np.zeros(160, dtype=np.float32)) == 0.0

    def test_빈_배열도_죽지_않는다(self):
        """장치가 빈 조각을 줄 수도 있다. 0으로 나누기 오류가 나면 안 된다."""
        assert compute_rms(np.array([], dtype=np.float32)) == 0.0

    @pytest.mark.parametrize("amplitude", [1.0, 0.5, 0.1])
    def test_사인파의_rms는_진폭_나누기_루트2(self, amplitude):
        """사인파의 RMS는 이론상 진폭/√2 다. 이 값이 맞아야 계산이 정상."""
        expected = amplitude / math.sqrt(2)
        assert compute_rms(make_sine(440, amplitude=amplitude)) == pytest.approx(expected, rel=0.01)

    def test_소리가_클수록_값도_크다(self):
        quiet = compute_rms(make_sine(440, amplitude=0.05))
        loud = compute_rms(make_sine(440, amplitude=0.8))
        assert loud > quiet

    def test_부호가_상쇄되지_않는다(self):
        """+와 -를 오가는 파형이라도 RMS는 0이 아니어야 한다(단순 평균과의 차이)."""
        alternating = np.array([0.5, -0.5, 0.5, -0.5], dtype=np.float32)
        assert compute_rms(alternating) == pytest.approx(0.5)


class TestRmsToDbfs:
    def test_최대치는_0dB(self):
        assert rms_to_dbfs(1.0) == pytest.approx(0.0)

    def test_절반이면_약_마이너스6dB(self):
        """진폭이 절반이면 -6dB 라는 오디오의 기본 상식과 맞아야 한다."""
        assert rms_to_dbfs(0.5) == pytest.approx(-6.02, abs=0.05)

    def test_무음은_하한값(self):
        """log(0)은 -무한대라 그대로 쓰면 화면이 깨진다. 하한으로 막는다."""
        assert rms_to_dbfs(0.0) == SILENCE_DBFS

    def test_음수가_들어와도_죽지_않는다(self):
        assert rms_to_dbfs(-0.1) == SILENCE_DBFS
