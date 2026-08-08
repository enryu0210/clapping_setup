"""음량 미터 막대 그리기 테스트.

화면 출력이라 사소해 보이지만, 칸 계산이 틀리면 막대가 범위를 벗어나 IndexError 로
프로그램이 죽는다. 실제 소리 없이 검증할 수 있는 부분이라 테스트로 못 박아둔다.
"""

from clap_launcher.ui.level_meter import METER_MIN_DBFS, METER_WIDTH, _make_bar


class TestMakeBar:
    def test_길이는_항상_일정하다(self):
        """길이가 들쭉날쭉하면 \\r 로 덮어쓸 때 이전 글자가 남는다."""
        for dbfs in (-200.0, METER_MIN_DBFS, -30.0, 0.0, 10.0):
            assert len(_make_bar(dbfs, dbfs)) == METER_WIDTH

    def test_무음이면_비어_있다(self):
        assert "█" not in _make_bar(METER_MIN_DBFS, METER_MIN_DBFS)

    def test_최대_음량이면_가득_찬다(self):
        assert _make_bar(0.0, 0.0) == "█" * METER_WIDTH

    def test_소리가_클수록_막대가_길다(self):
        quiet = _make_bar(-50.0, -50.0).count("█")
        loud = _make_bar(-10.0, -10.0).count("█")
        assert loud > quiet

    def test_범위를_벗어난_값도_죽지_않는다(self):
        """장치에 따라 0dB를 넘는 값이 들어올 수 있다(클리핑). 잘라내야 한다."""
        assert len(_make_bar(50.0, 50.0)) == METER_WIDTH
        assert len(_make_bar(-999.0, -999.0)) == METER_WIDTH

    def test_최고점_표시가_보인다(self):
        """박수는 순식간이라, 현재 음량이 내려가도 최고점은 남아 있어야 눈으로 본다."""
        assert "|" in _make_bar(-50.0, -10.0)

    def test_최고점이_현재값보다_낮으면_표시하지_않는다(self):
        """막대 안에 '|'가 묻혀 보이면 오히려 헷갈린다."""
        assert "|" not in _make_bar(-10.0, -50.0)
