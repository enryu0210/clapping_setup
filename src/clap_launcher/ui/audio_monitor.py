"""오디오 스레드 ↔ 화면(UI) 사이의 다리.

⚠️ 이 파일이 있는 이유 (GUI 프로그램의 가장 흔한 함정):
Tkinter 위젯은 **메인 스레드에서만** 건드릴 수 있다. 그런데 마이크 데이터는
오디오 라이브러리가 만든 다른 스레드에서 10ms마다 들어온다.
오디오 스레드에서 직접 라벨을 고치면 프로그램이 이유 없이 멈추거나 죽는다.

그래서 역할을 이렇게 나눈다.
  - 오디오 스레드 : 소리를 읽어 '최신 음량'만 여기에 적어둔다 (쓰기)
  - 화면 스레드   : 50ms마다 여기 적힌 값을 읽어 화면을 갱신한다 (읽기)
서로 직접 부르지 않고 이 객체를 통해서만 주고받는다.
"""

import threading
import time
from dataclasses import dataclass

from ..audio.features import SILENCE_DBFS, compute_rms, rms_to_dbfs
from ..audio.listener import AudioDeviceError, AudioListener
from ..config import DetectionConfig
from ..detector.clap_detector import ClapDetector, SoundEvent

PEAK_HOLD_SEC = 1.2       # 최고점을 몇 초간 붙잡아 둘지 (박수는 순식간이라 눈으로 못 본다)
LOUD_ENOUGH_DBFS = -45.0  # 이 정도 소리가 잡히면 "이 마이크 쓸 만하다"고 판단
RECENT_EVENT_LIMIT = 12   # 화면에 보여줄 최근 이벤트 개수


@dataclass(frozen=True)
class MonitorSnapshot:
    """화면이 읽어가는 '지금 상태' 한 장. 값이 도중에 바뀌지 않도록 통째로 복사해 넘긴다."""

    level_dbfs: float = SILENCE_DBFS
    peak_dbfs: float = SILENCE_DBFS
    session_max_dbfs: float = SILENCE_DBFS   # 이 장치로 들은 것 중 가장 큰 소리
    device_desc: str = ""                    # 실제로 열린 장치 사양 설명
    error: str = ""                          # 비어 있지 않으면 화면에 빨갛게 보여준다
    running: bool = False

    # ── 박수 감지 관련 (감지를 켰을 때만 채워진다) ──
    events: tuple[SoundEvent, ...] = ()      # 최근 분석한 소리들 (걸러진 것 포함)
    trigger_count: int = 0                   # '짝짝'이 완성된 횟수
    last_trigger_at: float = 0.0             # 마지막 발동 시각 (monotonic)

    @property
    def is_loud_enough(self) -> bool:
        """이 마이크로 박수가 잡히는지 여부. 마이크 선택 화면에서 ✅ 표시에 쓴다."""
        return self.session_max_dbfs >= LOUD_ENOUGH_DBFS


class AudioMonitor:
    """마이크를 열어 음량을 계속 재는 백그라운드 일꾼.

    사용법:
        monitor = AudioMonitor()
        monitor.start(device=3)      # 장치를 바꿀 때도 그냥 다시 start 하면 된다
        snapshot = monitor.snapshot()
        monitor.stop()
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()          # 두 스레드가 동시에 값을 만지지 않도록
        self._snapshot = MonitorSnapshot()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def snapshot(self) -> MonitorSnapshot:
        """지금 상태를 한 장 떠서 돌려준다. 화면 쪽에서 부른다."""
        with self._lock:
            return self._snapshot

    def _update(self, **changes) -> None:
        """상태 일부만 바꿔서 새 스냅샷으로 교체한다."""
        with self._lock:
            current = self._snapshot.__dict__
            self._snapshot = MonitorSnapshot(**{**current, **changes})

    def start(self, device: int | str | None,
              detection: DetectionConfig | None = None) -> None:
        """지정한 마이크로 측정을 시작한다. 이미 돌고 있으면 멈추고 새로 연다.

        Args:
            detection: 주면 박수 감지까지 돌린다. None이면 음량만 잰다
                       (마이크 선택 화면에서는 감지가 필요 없다).
        """
        self.stop()
        self._stop_event = threading.Event()
        # 장치를 바꾸면 이전 장치의 측정값은 의미가 없으므로 초기화한다
        self._update(
            level_dbfs=SILENCE_DBFS, peak_dbfs=SILENCE_DBFS, session_max_dbfs=SILENCE_DBFS,
            device_desc="", error="", running=True,
            events=(), trigger_count=0, last_trigger_at=0.0,
        )
        # daemon=True : 창을 강제로 닫아도 이 스레드가 프로그램을 붙잡고 있지 않게
        self._thread = threading.Thread(
            target=self._run, args=(device, detection, self._stop_event),
            daemon=True, name="audio-monitor",
        )
        self._thread.start()

    def stop(self) -> None:
        """측정을 멈춘다. 스레드가 실제로 끝날 때까지 잠깐 기다린다."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            # 마이크에서 조각을 기다리는 중일 수 있어 최대 1.5초까지 기다린다.
            # 그래도 안 끝나면 daemon 스레드라 프로그램 종료를 막지는 않는다.
            thread.join(timeout=1.5)
        self._thread = None
        self._update(running=False)

    def _run(self, device: int | str | None, detection: DetectionConfig | None,
             stop_event: threading.Event) -> None:
        """오디오 스레드 본체. 여기서는 절대 화면 위젯을 건드리지 않는다."""
        try:
            with AudioListener(device) as listener:
                self._update(device_desc=listener.spec.describe())
                peak_dbfs, peak_time = SILENCE_DBFS, time.monotonic()

                # 감지기는 실제로 열린 샘플레이트를 알아야 한다.
                # 16000Hz 라고 가정하면 44100Hz로 열린 장치에서 주파수 계산이 전부 어긋난다.
                detector = (ClapDetector(detection, listener.spec.sample_rate)
                            if detection is not None else None)

                for frame in listener.frames():
                    if stop_event.is_set():
                        break

                    now = time.monotonic()
                    dbfs = rms_to_dbfs(compute_rms(frame))

                    # 최고점 유지: 더 큰 소리가 오거나, 유지 시간이 지나면 갱신
                    if dbfs > peak_dbfs or now - peak_time > PEAK_HOLD_SEC:
                        peak_dbfs, peak_time = dbfs, now

                    snapshot = self.snapshot()
                    changes = {
                        "level_dbfs": dbfs,
                        "peak_dbfs": peak_dbfs,
                        "session_max_dbfs": max(snapshot.session_max_dbfs, dbfs),
                    }

                    if detector is not None:
                        event = detector.feed(frame, now)
                        if event is not None:
                            # 최근 것만 남긴다 (오래된 이벤트는 화면에도 안 보인다)
                            changes["events"] = (snapshot.events + (event,))[-RECENT_EVENT_LIMIT:]
                            if event.triggered:
                                changes["trigger_count"] = snapshot.trigger_count + 1
                                changes["last_trigger_at"] = now

                    self._update(**changes)
        except AudioDeviceError as exc:
            # 마이크 문제는 사용자가 고칠 수 있는 문제다. 화면에 그대로 보여준다.
            self._update(error=str(exc), running=False)
        except Exception as exc:  # 예상 못 한 오류로 창까지 죽는 일은 없어야 한다
            self._update(error=f"예상치 못한 오류가 발생했습니다: {exc}", running=False)
        else:
            self._update(running=False)
