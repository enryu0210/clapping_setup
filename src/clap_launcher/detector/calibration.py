"""보정(calibration) — 사용자의 실제 소리로 기준값을 정한다.

⚠️ 이 파일의 핵심 교훈 (실제로 실패하고 나서 고친 것):

처음에는 **박수 샘플만** 받아서 기준을 정했다. "내 박수가 이 범위에 들어오게" 하는 방식이다.
그런데 마이크가 고음을 덜 잡는 경우, 박수의 고음 비율이 낮게 측정되고,
거기에 여유까지 붙이면 경계선이 훨씬 낮아진다. 그렇게 넓어진 범위 안에
**키보드 소리가 통째로 들어와 버렸다.** (재현 결과: 키보드 5개 중 5개 통과)

무엇을 받아들일지만 알려주고 **무엇을 배제해야 하는지는 알려준 적이 없으니** 당연한 결과다.

그래서 지금은 두 가지를 함께 받는다.
  · 박수 샘플 (positive)  : 이 안에는 반드시 들어와야 한다
  · 잡음 샘플 (negative)  : 타이핑·클릭 등. 이건 반드시 배제해야 한다

경계선은 두 무리 **사이**에 긋는다. 한쪽만 보고 정하지 않는다.
"""

from dataclasses import dataclass, replace

from ..audio.features import EventFeatures
from ..config import DetectionConfig

REQUIRED_SAMPLES = 5          # 보정에 필요한 박수 횟수
NOISE_COLLECT_SEC = 10.0      # 잡음(타이핑 등)을 모으는 시간
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
    noise_count: int = 0
    rejected_noise: int = 0        # 잡음 샘플 중 실제로 배제된 개수
    limiter_suspected: bool = False
    warnings: tuple[str, ...] = ()

    @property
    def noise_blocked_ratio(self) -> float:
        """잡음을 얼마나 잘 막아내는지 (0~1). 화면에 성적표처럼 보여준다."""
        return self.rejected_noise / self.noise_count if self.noise_count else 0.0


# 잡음이 박수 바로 옆에 있어도 경계선을 이 정도는 떨어뜨려 둔다.
# 이유: 보정에 쓴 5번의 박수가 그 사람의 모든 박수를 대표하지는 않는다.
# 관측값에 딱 붙여 경계를 그으면 조금만 다르게 친 박수가 바로 탈락한다.
# (실제로 "길이 24~30ms" 같은 지나치게 좁은 창이 만들어지는 것을 확인했다)
# 여기서 못 막은 잡음은 다른 특징이 잡거나, 경고로 사용자에게 알린다.
SAFETY_HEADROOM_LOW = 0.85    # 하한은 박수 최솟값의 85% 아래에 둔다
SAFETY_HEADROOM_HIGH = 1.18   # 상한은 박수 최댓값의 118% 위에 둔다


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _lower_bound(positives: list[float], negatives: list[float],
                 margin: float, limits: tuple[float, float]) -> float:
    """'이 값 이상이어야 박수' 경계선을 정한다.

    박수의 최솟값보다 아래에 긋되(박수를 놓치면 안 되므로),
    그 아래에 있는 잡음은 최대한 잘라낸다. 잡음이 박수보다 위에 있으면
    이 특징으로는 구분이 안 되는 것이므로 건드리지 않는다(다른 특징이 잡아준다).
    """
    lowest_clap = min(positives)
    bound = lowest_clap * margin                       # 박수만 보고 정한 기본 경계

    below = [v for v in negatives if v < lowest_clap]   # 이 특징으로 자를 수 있는 잡음들
    if below:
        # 가장 까다로운 잡음과 가장 약한 박수의 중간에 긋는다
        bound = max(bound, (max(below) + lowest_clap) / 2)

    # 잡음이 아무리 가까워도 박수 쪽으로 너무 바짝 붙이지는 않는다
    bound = min(bound, lowest_clap * SAFETY_HEADROOM_LOW)
    return _clamp(bound, *limits)


def _upper_bound(positives: list[float], negatives: list[float],
                 margin: float, limits: tuple[float, float]) -> float:
    """'이 값 이하여야 박수' 경계선. 위와 같은 논리를 반대 방향으로."""
    highest_clap = max(positives)
    bound = highest_clap * margin

    above = [v for v in negatives if v > highest_clap]
    if above:
        bound = min(bound, (min(above) + highest_clap) / 2)

    bound = max(bound, highest_clap * SAFETY_HEADROOM_HIGH)
    return _clamp(bound, *limits)


def derive_config(samples: list[EventFeatures],
                  noise: list[EventFeatures] | None = None,
                  base: DetectionConfig | None = None) -> CalibrationResult:
    """박수 샘플(+선택적으로 잡음 샘플)에서 기준값을 계산한다.

    Args:
        samples: 사용자가 친 박수의 특징값
        noise: 배제해야 할 소리(타이핑·클릭 등)의 특징값. 주면 훨씬 정확해진다.
        base: 기준으로 삼을 설정 (간격·쿨다운 등은 그대로 유지된다)

    Raises:
        ValueError: 박수 샘플이 하나도 없을 때
    """
    if not samples:
        raise ValueError("보정하려면 박수 샘플이 최소 1개는 필요합니다.")

    base = base or DetectionConfig()
    noise = noise or []
    warnings: list[str] = []

    def clap_values(getter):
        return [getter(f) for f in samples]

    def noise_values(getter):
        return [getter(f) for f in noise]

    config = replace(
        base,
        min_high_freq_ratio=_lower_bound(
            clap_values(lambda f: f.high_freq_ratio),
            noise_values(lambda f: f.high_freq_ratio), 0.75, (0.20, 0.90)),
        min_zero_crossing_rate=_lower_bound(
            clap_values(lambda f: f.zero_crossing_rate),
            noise_values(lambda f: f.zero_crossing_rate), 0.70, (0.10, 0.80)),
        min_flatness=_lower_bound(
            clap_values(lambda f: f.flatness),
            noise_values(lambda f: f.flatness), 0.60, (0.03, 0.40)),
        min_decay_ms=_lower_bound(
            clap_values(lambda f: f.decay_ms),
            noise_values(lambda f: f.decay_ms), 0.55, (3.0, 40.0)),
        max_flatness=_upper_bound(
            clap_values(lambda f: f.flatness),
            noise_values(lambda f: f.flatness), 1.40, (0.30, 0.85)),
        max_harmonicity=_upper_bound(
            clap_values(lambda f: f.harmonicity),
            noise_values(lambda f: f.harmonicity), 1.35, (0.25, 0.75)),
        max_decay_ms=_upper_bound(
            clap_values(lambda f: f.decay_ms),
            noise_values(lambda f: f.decay_ms), 1.60, (30.0, 150.0)),
    )

    rejected = sum(1 for f in noise if _rejected_by(config, f))

    # ── 사용자에게 알려줄 만한 관찰 ──
    crest = clap_values(lambda f: f.crest_factor)
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

    if not noise:
        warnings.append(
            "잡음 수집을 건너뛰었습니다. 타이핑이나 클릭 소리에 반응한다면 "
            "다시 보정하면서 2단계(평소 소리 내기)를 꼭 진행해 주세요."
        )
    elif rejected < len(noise):
        leaked = len(noise) - rejected
        warnings.append(
            f"수집한 잡음 {len(noise)}개 중 {leaked}개는 박수와 구분되지 않았습니다. "
            "그 소리가 박수와 물리적으로 너무 비슷하다는 뜻입니다. "
            "마이크를 입 쪽이 아니라 손 쪽에 가깝게 두거나, 박수를 더 세게 쳐보세요."
        )

    high_freq = clap_values(lambda f: f.high_freq_ratio)
    if max(high_freq) - min(high_freq) > 0.35:
        warnings.append(
            "박수마다 소리 성질이 크게 달랐습니다. 마이크와의 거리를 일정하게 하고 "
            "다시 보정하면 더 정확해집니다."
        )

    return CalibrationResult(
        config=config,
        sample_count=len(samples),
        noise_count=len(noise),
        rejected_noise=rejected,
        limiter_suspected=limiter_suspected,
        warnings=tuple(warnings),
    )


def _rejected_by(config: DetectionConfig, f: EventFeatures) -> bool:
    """이 설정이 해당 소리를 걸러내는가.

    판정 규칙이 두 군데로 갈라지지 않도록 실제 감지기의 판정 함수를 그대로 쓴다.
    (규칙을 여기에 한 번 더 적으면 반드시 한쪽이 낡는다)
    """
    from .clap_detector import ClapDetector

    return ClapDetector(config, sample_rate=16000)._reject_reason(f) != ""
