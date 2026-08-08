"""M1: 콘솔 음량 미터 — "마이크가 내 소리를 듣고 있나?"를 눈으로 확인하는 도구.

박수 감지를 만들기 전에 이게 먼저 필요한 이유:
감지가 안 될 때 원인이 (1) 마이크가 아예 안 들리는 것인지 (2) 감지 로직이 잘못된 것인지
구분할 수 없으면 디버깅이 불가능하다. 이 미터로 (1)을 먼저 배제한다.

사용법: python -m clap_launcher --level
"""

import sys
import time

from ..audio.features import compute_rms, rms_to_dbfs
from ..audio.listener import AudioListener

METER_WIDTH = 40        # 막대 칸 수
METER_MIN_DBFS = -60.0  # 이보다 조용하면 막대가 비어 있음 (조용한 방 수준)
REFRESH_INTERVAL = 0.05  # 화면 갱신 주기(초). 10ms마다 다시 그리면 눈이 아프고 느려진다.
PEAK_HOLD_SEC = 1.5     # 최고점 표시를 몇 초간 붙잡아 둘지 (박수는 순식간이라 눈으로 못 봄)


def _make_bar(dbfs: float, peak_dbfs: float) -> str:
    """dBFS 값을 막대 문자열로. 최고점은 '|'로 따로 표시한다."""
    def to_cells(value: float) -> int:
        ratio = (value - METER_MIN_DBFS) / (0.0 - METER_MIN_DBFS)
        return max(0, min(METER_WIDTH, round(ratio * METER_WIDTH)))

    filled = to_cells(dbfs)
    peak_pos = to_cells(peak_dbfs)

    cells = ["█" if i < filled else "·" for i in range(METER_WIDTH)]
    # 최고점 표시가 막대 안에 묻히지 않도록, 채워진 부분 바깥일 때만 그린다.
    if peak_pos > filled and peak_pos > 0:
        cells[min(peak_pos - 1, METER_WIDTH - 1)] = "|"
    return "".join(cells)


def run_level_meter(device: int | str | None = None, duration: float | None = None) -> int:
    """마이크 음량을 실시간으로 콘솔에 그린다.

    Args:
        device: 장치 번호나 이름 일부. None이면 Windows 기본 입력 장치.
        duration: 몇 초 동안 돌지. None이면 Ctrl+C 전까지 계속.

    Returns:
        종료 코드 (0=정상). 소리가 전혀 안 잡히면 2를 반환해 문제를 알린다.
    """
    with AudioListener(device) as listener:
        print(f"🎤 입력 장치: {listener.spec.describe()}")
        print("   박수를 치면 막대가 확 튀어야 정상입니다. (Ctrl+C 로 종료)\n")

        started = time.monotonic()
        last_draw = 0.0
        peak_dbfs, peak_time = METER_MIN_DBFS, started
        session_max_dbfs = METER_MIN_DBFS

        try:
            for frame in listener.frames():
                now = time.monotonic()
                dbfs = rms_to_dbfs(compute_rms(frame))
                session_max_dbfs = max(session_max_dbfs, dbfs)

                # 최고점 유지: 더 큰 소리가 오거나, 유지 시간이 지나면 갱신
                if dbfs > peak_dbfs or now - peak_time > PEAK_HOLD_SEC:
                    peak_dbfs, peak_time = dbfs, now

                # 모든 조각(10ms)마다 그리면 출력이 병목이 된다. 50ms마다만 그린다.
                if now - last_draw >= REFRESH_INTERVAL:
                    last_draw = now
                    bar = _make_bar(dbfs, peak_dbfs)
                    # \r 로 같은 줄을 덮어써서 한 줄짜리 미터처럼 보이게 한다.
                    sys.stdout.write(f"\r[{bar}] {dbfs:7.1f} dBFS  최고 {peak_dbfs:6.1f}")
                    sys.stdout.flush()

                if duration is not None and now - started >= duration:
                    break
        except KeyboardInterrupt:
            pass  # Ctrl+C 는 정상 종료로 취급한다 (아래 요약을 출력해야 하므로)

        print(f"\n\n측정 종료 — 이번 세션 최대 음량: {session_max_dbfs:.1f} dBFS")
        if listener.dropped_frames:
            print(f"⚠️  처리가 밀려 버린 조각: {listener.dropped_frames}개 (성능 확인 필요)")

        # 소리가 사실상 없었다면 장치 선택이 잘못됐을 가능성이 높다.
        if session_max_dbfs <= METER_MIN_DBFS + 5:
            print(
                "⚠️  소리가 거의 잡히지 않았습니다.\n"
                "    --list-devices 로 목록을 보고 --device 번호로 다른 마이크를 지정해 보세요.\n"
                "    (가상 오디오 장치는 해당 앱이 실행 중이 아니면 무음만 나옵니다)"
            )
            return 2
    return 0
