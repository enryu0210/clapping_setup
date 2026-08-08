"""보정(calibration) — 사용자의 실제 박수로 기준값을 정한다.

왜 필요한가:
기본 기준값은 합성 신호로 정한 '평균적인 박수' 기준이다. 그런데 실제 값은
마이크 특성(고음이 얼마나 살아 있는지), 리미터·노이즈 제거 같은 소프트웨어 처리,
방의 울림, 손 모양과 박수 방식에 따라 꽤 달라진다.

그래서 **그 사람이 그 마이크로 친 진짜 박수**를 몇 번 받아서 기준을 다시 잡는다.
이러면 리미터가 걸려 있든 아니든, 그 환경에서 나오는 실제 값이 기준이 된다.

⚠️ 여유(margin)를 넉넉히 두는 이유:
5번 친 박수가 그 사람의 모든 박수를 대표하지는 않는다. 잰 값을 그대로 경계선으로
쓰면 조금만 다르게 쳐도 안 잡힌다. 관측 범위보다 넓게 잡아야 실사용에서 견딘다.
"""

from dataclasses import dataclass, replace

from ..audio.features import EventFeatures
from ..config import DetectionConfig

REQUIRED_SAMPLES = 5          # 보정에 필요한 박수 횟수
LIMITER_CREST_HINT = 5.0      # 이보다 낮으면 리미터가 걸려 있을 가능성이 높다

# 보정 샘플로 받아줄 최소 크기(진폭). 약 -34dBFS.
# 판정에는 절대 크기를 안 쓰지만 **보정에서는 쓴다.** 보정은 사용자가 마이크 앞에서
# 일부러 크게 치는 상황이라, 이보다 작은 소리는 의도한 박수가 아니라 주변 소음일 확률이 높다.
# 이 문턱이 없으면 에어컨·의자 소리가 샘플로 섞여 기준값 전체가 망가진다.
MIN_SAMPLE_PEAK = 0.02


@dataclass(frozen=True)
class CalibrationResult:
    """보정 결과와, 사용자에게 알려줄 만한 관찰 사항."""

    config: DetectionConfig
    sample_count: int
    limiter_suspected: bool
    warnings: tuple[str, ...] = ()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def derive_config(samples: list[EventFeatures],
                  base: DetectionConfig | None = None) -> CalibrationResult:
    """모은 박수 샘플에서 기준값을 계산한다.

    각 특징마다 '관측된 범위'를 구하고, 거기에 여유를 붙여 경계선으로 삼는다.
    말도 안 되는 값이 나오지 않도록 상식적인 범위 안으로 잘라낸다(_clamp).

    Raises:
        ValueError: 샘플이 하나도 없을 때
    """
    if not samples:
        raise ValueError("보정하려면 박수 샘플이 최소 1개는 필요합니다.")

    base = base or DetectionConfig()
    warnings: list[str] = []

    high_freq = [f.high_freq_ratio for f in samples]
    flatness = [f.flatness for f in samples]
    zcr = [f.zero_crossing_rate for f in samples]
    harmonicity = [f.harmonicity for f in samples]
    decay = [f.decay_ms for f in samples]
    crest = [f.crest_factor for f in samples]

    config = replace(
        base,
        # 하한: 관측 최솟값보다 넉넉히 아래로
        min_high_freq_ratio=_clamp(min(high_freq) * 0.75, 0.20, 0.90),
        min_zero_crossing_rate=_clamp(min(zcr) * 0.70, 0.10, 0.80),
        min_flatness=_clamp(min(flatness) * 0.60, 0.03, 0.40),
        # 상한: 관측 최댓값보다 넉넉히 위로
        max_flatness=_clamp(max(flatness) * 1.40, 0.30, 0.85),
        max_harmonicity=_clamp(max(harmonicity) * 1.35, 0.25, 0.75),
        max_decay_ms=_clamp(max(decay) * 1.60, 30.0, 150.0),
    )

    # ── 사용자에게 알려줄 만한 관찰 ──
    average_crest = sum(crest) / len(crest)
    limiter_suspected = average_crest < LIMITER_CREST_HINT
    if limiter_suspected:
        warnings.append(
            "이 마이크는 소리가 눌려 있습니다(리미터·컴프레서로 보임). "
            "감지는 소리의 '모양'으로 하므로 동작에는 문제없지만, "
            "가능하면 처리를 거치지 않은 마이크 직결 장치를 고르는 편이 정확합니다."
        )

    if len(samples) < REQUIRED_SAMPLES:
        warnings.append(
            f"샘플이 {len(samples)}개뿐이라 기준이 덜 정확할 수 있습니다. "
            f"{REQUIRED_SAMPLES}번 이상 치는 것을 권합니다."
        )

    # 박수마다 값이 들쭉날쭉하면 마이크가 소리를 제대로 못 잡고 있을 수 있다
    if max(high_freq) - min(high_freq) > 0.35:
        warnings.append(
            "박수마다 소리 성질이 크게 달랐습니다. 마이크와의 거리를 일정하게 하고 "
            "다시 보정하면 더 정확해집니다."
        )

    return CalibrationResult(
        config=config,
        sample_count=len(samples),
        limiter_suspected=limiter_suspected,
        warnings=tuple(warnings),
    )
