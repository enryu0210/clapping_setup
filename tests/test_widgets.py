"""음량 막대의 계산 부분 테스트.

화면 그리기 자체는 자동 테스트가 어렵지만, '값 → 막대 비율' 계산은 순수 함수라
창을 띄우지 않고 검증할 수 있다. 이 계산이 틀리면 막대가 안 움직이거나 범위를 벗어난다.
"""

import pytest

from clap_launcher.ui.widgets import METER_MIN_DBFS, METER_SEGMENTS, dbfs_to_ratio, segment_color


class TestDbfsToRatio:
    def test_무음이면_0(self):
        assert dbfs_to_ratio(METER_MIN_DBFS) == 0.0

    def test_최대치면_1(self):
        assert dbfs_to_ratio(0.0) == 1.0

    def test_중간값은_중간_비율(self):
        assert dbfs_to_ratio(METER_MIN_DBFS / 2) == pytest.approx(0.5)

    def test_소리가_클수록_비율도_크다(self):
        assert dbfs_to_ratio(-10.0) > dbfs_to_ratio(-40.0)

    @pytest.mark.parametrize("dbfs", [-999.0, -120.0, 0.0, 12.0, 999.0])
    def test_어떤_값이_와도_0과_1_사이(self, dbfs):
        """클리핑으로 0dB를 넘는 값이 실제로 들어온다. 잘라내지 않으면 막대가 넘친다."""
        assert 0.0 <= dbfs_to_ratio(dbfs) <= 1.0


class TestSegmentColor:
    def test_모든_칸이_색을_갖는다(self):
        for i in range(METER_SEGMENTS):
            assert segment_color(i, METER_SEGMENTS).startswith("#")

    def test_왼쪽과_오른쪽_끝의_색이_다르다(self):
        """작은 소리(초록)와 찌그러지는 소리(빨강)를 눈으로 구분할 수 있어야 한다."""
        assert segment_color(0, METER_SEGMENTS) != segment_color(METER_SEGMENTS - 1, METER_SEGMENTS)

    def test_칸이_하나여도_죽지_않는다(self):
        """0으로 나누기 사고 방지."""
        assert segment_color(0, 1).startswith("#")
