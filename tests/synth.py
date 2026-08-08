"""테스트용 소리 합성기 — 마이크 없이 감지기를 검증하기 위한 도구.

실제 박수를 녹음해서 테스트하면 파일이 저장소에 들어가고, 그 사람의 마이크·방에
맞춰진 결과라 다른 환경을 대변하지 못한다. 물리적 특성을 흉내 낸 합성 신호를 쓰면
"어떤 성질 때문에 걸러지는가"를 정확히 겨냥해 검증할 수 있다.

여기서 만드는 소리들의 특징값은 docs/DETECTION.md 3장의 표와 일치한다.
"""

import numpy as np

SAMPLE_RATE = 16000
FRAME_SIZE = 160        # 10ms


def _envelope(n: int, attack_ms: float, decay_ms: float) -> np.ndarray:
    """소리의 봉투: 빠르게 커졌다가(attack) 서서히 잦아든다(decay)."""
    t = np.arange(n) / SAMPLE_RATE * 1000
    rise = np.clip(t / max(attack_ms, 0.1), 0, 1)
    fall = np.exp(-np.maximum(t - attack_ms, 0) / decay_ms)
    return rise * fall


def clap(rng: np.random.Generator, duration_ms: float = 80) -> np.ndarray:
    """👏 박수: 공기가 터지는 넓은 대역 잡음 + 아주 빠른 감쇠 + 고음 강조."""
    n = int(SAMPLE_RATE * duration_ms / 1000)
    noise = np.diff(rng.normal(0, 1, n), prepend=0)   # 미분 = 고음 강조
    return noise * _envelope(n, 0.5, 12)


def cough(rng: np.random.Generator, duration_ms: float = 300) -> np.ndarray:
    """🤧 기침: 성대 진동(음정)이 섞이고 길게 끌린다. 가장 중요한 오탐 대상."""
    n = int(SAMPLE_RATE * duration_ms / 1000)
    t = np.arange(n) / SAMPLE_RATE
    voiced = sum(np.sin(2 * np.pi * 130 * k * t) / k for k in range(1, 12))
    return (voiced + rng.normal(0, 0.45, n)) * _envelope(n, 18, 90)


def speech(rng: np.random.Generator, duration_ms: float = 350) -> np.ndarray:
    """🗣️ 말소리 '아': 뚜렷한 음정이 계속 이어진다."""
    n = int(SAMPLE_RATE * duration_ms / 1000)
    t = np.arange(n) / SAMPLE_RATE
    tone = sum(np.sin(2 * np.pi * 110 * k * t + k) / k for k in range(1, 20))
    return (tone + rng.normal(0, 0.05, n)) * _envelope(n, 40, 400)


def door_slam(rng: np.random.Generator, duration_ms: float = 200) -> np.ndarray:
    """🚪 문 닫는 소리: 크지만 저음 덩어리."""
    n = int(SAMPLE_RATE * duration_ms / 1000)
    noise = rng.normal(0, 1, n)
    spectrum = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1 / SAMPLE_RATE)
    spectrum[freqs > 500] *= 0.05                     # 저역만 남긴다
    return np.fft.irfft(spectrum, n) * _envelope(n, 2, 45)


def paper(rng: np.random.Generator, duration_ms: float = 250) -> np.ndarray:
    """📄 종이 구기기: 고음 잡음이라 박수와 지문이 거의 같다. **길이로만 구분된다.**"""
    n = int(SAMPLE_RATE * duration_ms / 1000)
    noise = np.diff(rng.normal(0, 1, n), prepend=0)
    return noise * _envelope(n, 30, 200)


def keyboard(rng: np.random.Generator, duration_ms: float = 25) -> np.ndarray:
    """⌨️ 키보드: 짧고 넓은 대역. 박수와 헷갈리기 쉽다."""
    n = int(SAMPLE_RATE * duration_ms / 1000)
    return rng.normal(0, 1, n) * _envelope(n, 0.3, 5)


def normalize(sound: np.ndarray, peak: float = 0.7) -> np.ndarray:
    """소리의 최대 진폭을 맞춘다."""
    largest = np.abs(sound).max()
    return sound * (peak / largest) if largest > 0 else sound


def build_stream(events: list[tuple[float, np.ndarray]], duration_sec: float,
                 rng: np.random.Generator, noise_level: float = 0.0005) -> np.ndarray:
    """배경 잡음이 깔린 타임라인에 소리들을 심어 하나의 오디오로 만든다.

    Args:
        events: (시각(초), 소리) 목록
        duration_sec: 전체 길이
        noise_level: 조용한 방 수준의 배경 잡음
    """
    total = int(SAMPLE_RATE * duration_sec)
    stream = rng.normal(0, noise_level, total)
    for at_sec, sound in events:
        start = int(SAMPLE_RATE * at_sec)
        end = min(total, start + sound.size)
        if start < total:
            stream[start:end] += sound[: end - start]
    return stream.astype(np.float32)


def apply_limiter(stream: np.ndarray, threshold_db: float = -18.0,
                  attack_ms: float = 1.0, release_ms: float = 80.0,
                  makeup_db: float = 10.0) -> np.ndarray:
    """클리핑 가드(리미터)를 흉내 낸다. Wave Link 같은 프로그램이 하는 일이다.

    ⚠️ 반드시 **스트림 전체에** 걸어야 의미가 있다.
    소리 하나하나에 따로 걸면 리미터의 진짜 위험인 '펌핑'이 재현되지 않는다.
    펌핑 = 첫 박수 때 깎인 볼륨이 서서히 돌아오는 동안 두 번째 박수가 작게 들어오는 현상.
    두 번째 박수를 놓치는 원인이 바로 이것이라, 테스트에서 반드시 확인해야 한다.
    """
    threshold = 10 ** (threshold_db / 20)
    attack = np.exp(-1 / (SAMPLE_RATE * attack_ms / 1000))
    release = np.exp(-1 / (SAMPLE_RATE * release_ms / 1000))

    gain = 1.0
    output = np.empty_like(stream)
    for i, sample in enumerate(stream):
        level = abs(sample)
        target = min(1.0, threshold / level) if level > threshold else 1.0
        coefficient = attack if target < gain else release
        gain = coefficient * gain + (1 - coefficient) * target
        output[i] = sample * gain

    output *= 10 ** (makeup_db / 20)          # 리미터 뒤 볼륨 보정
    return np.clip(output, -1.0, 1.0).astype(np.float32)


def frames_of(stream: np.ndarray):
    """스트림을 10ms 조각으로 잘라 (조각, 시각) 으로 내준다."""
    for index in range(0, len(stream) - FRAME_SIZE + 1, FRAME_SIZE):
        yield stream[index : index + FRAME_SIZE], index / SAMPLE_RATE
