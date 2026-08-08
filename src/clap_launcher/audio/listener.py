"""[1] 마이크 입력 — sounddevice 로 소리 조각(frame)을 계속 읽어온다.

설정값 근거:
  - 16000Hz : 박수 판별에 필요한 고음(2~8kHz)까지 담기면서 계산량이 가볍다.
  - 모노    : 방향 정보는 필요 없다. 스테레오 장치면 평균 내서 합친다.
  - 10ms 조각 : 박수는 50ms 안에 끝나므로, 조각이 크면 순간 피크가 평균에 묻힌다.

⚠️ 실제 PC에서 확인한 문제 (그래서 '협상' 방식으로 구현함):
   PC에 달린 마이크들은 대부분 44100Hz / 스테레오이고, 오디오 인터페이스나
   Elgato Wave Link 같은 가상 장치까지 섞이면 입력 장치가 수십 개가 된다.
   여기에 대고 "무조건 16000Hz 모노로 열어" 하면 장치에 따라 그냥 실패한다.
   그래서 원하는 설정을 먼저 시도하고, 안 되면 장치가 지원하는 값으로 물러선다.
   실제 사용된 값은 StreamSpec 으로 밖에 알려줘서 뒷단이 그 값을 쓰게 한다.

⚠️ 프라이버시: 여기서 읽은 오디오는 파일로 저장하지도, 네트워크로 보내지도 않는다.
"""

import queue
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

PREFERRED_SAMPLE_RATE = 16000   # Hz — 되면 이걸 쓰고, 안 되면 장치 기본값으로 물러선다
FRAME_DURATION_SEC = 0.01       # 조각 하나의 길이 = 10ms
QUEUE_MAX_FRAMES = 200          # 약 2초치. 소비가 밀리면 오래된 조각을 버린다


class AudioDeviceError(Exception):
    """마이크를 열 수 없을 때. 메시지에 원인과 해결 방법을 함께 담는다."""


@dataclass(frozen=True)
class StreamSpec:
    """실제로 열린 스트림의 사양. '원한 값'이 아니라 '협상 결과'다."""

    device_index: int
    device_name: str
    sample_rate: int
    channels: int
    frame_size: int          # 조각 하나의 샘플 수

    def describe(self) -> str:
        ch = "모노" if self.channels == 1 else f"{self.channels}채널"
        return (
            f"[{self.device_index}] {self.device_name} "
            f"({self.sample_rate}Hz, {ch}, {self.frame_size}샘플/조각)"
        )


def list_input_devices() -> list[tuple[int, str]]:
    """입력 가능한 장치 목록을 (번호, 이름)으로 돌려준다.

    같은 마이크가 MME/DirectSound/WASAPI 별로 여러 번 나오는 것이 정상이다.
    사용자가 --device 로 고를 수 있게 보여주는 용도.
    """
    devices = []
    for index, info in enumerate(sd.query_devices()):
        if info["max_input_channels"] > 0:
            host_api = sd.query_hostapis(info["hostapi"])["name"]
            devices.append((index, f"{info['name']} ({host_api})"))
    return devices


def _resolve_device_index(device: int | str | None) -> int:
    """설정에 적힌 장치(번호 또는 이름 일부)를 실제 장치 번호로 바꾼다."""
    if device is None:
        default = sd.default.device[0]     # (입력, 출력) 중 입력 쪽
        if default is None or default < 0:
            raise AudioDeviceError(
                "기본 입력 장치가 없습니다. 마이크가 연결돼 있는지 확인하거나, "
                "--list-devices 로 목록을 보고 --device 번호로 직접 지정하세요."
            )
        return int(default)

    if isinstance(device, int):
        return device

    # 문자열이면 이름 일부로 찾는다 (예: "Wave" -> Elgato Wave)
    matches = [i for i, name in list_input_devices() if device.lower() in name.lower()]
    if not matches:
        raise AudioDeviceError(
            f"'{device}' 라는 이름의 입력 장치를 찾지 못했습니다. "
            "--list-devices 로 실제 이름을 확인하세요."
        )
    return matches[0]


def resolve_stream_spec(device: int | str | None = None) -> StreamSpec:
    """장치와 '협상'해서 실제로 열 수 있는 사양을 정한다.

    순서:
      1) 채널 : 모노(1)를 먼저 시도, 안 되면 장치 최대 채널(최대 2)
      2) 샘플레이트 : 16000Hz 를 먼저 시도, 안 되면 장치 기본값
    둘 다 실패하면 AudioDeviceError.
    """
    index = _resolve_device_index(device)
    try:
        info = sd.query_devices(index)
    except Exception as exc:  # 번호가 범위를 벗어난 경우 등
        raise AudioDeviceError(f"장치 {index} 정보를 읽을 수 없습니다: {exc}") from exc

    if info["max_input_channels"] < 1:
        raise AudioDeviceError(
            f"장치 [{index}] {info['name']} 는 입력용이 아닙니다(출력 전용). "
            "--list-devices 로 입력 장치를 고르세요."
        )

    max_channels = min(int(info["max_input_channels"]), 2)
    device_rate = int(info["default_samplerate"])

    # 가능한 조합을 선호 순서대로 시도한다.
    for channels in (1, max_channels):
        for rate in (PREFERRED_SAMPLE_RATE, device_rate):
            try:
                sd.check_input_settings(device=index, channels=channels, samplerate=rate)
            except Exception:
                continue
            return StreamSpec(
                device_index=index,
                device_name=str(info["name"]),
                sample_rate=rate,
                channels=channels,
                frame_size=int(rate * FRAME_DURATION_SEC),
            )

    raise AudioDeviceError(
        f"장치 [{index}] {info['name']} 를 열 수 있는 설정을 찾지 못했습니다. "
        "다른 앱이 마이크를 독점 중일 수 있습니다. "
        "Windows 설정 > 개인 정보 > 마이크 권한도 확인하세요."
    )


class AudioListener:
    """마이크 스트림을 열고 조각을 하나씩 넘겨주는 객체.

    다른 앱(화상회의 등)과 동시에 쓸 수 있도록 공유 모드로 연다.
    독점 모드로 열면 회의 중 마이크를 빼앗는 문제가 생긴다. (sounddevice 기본값이 공유 모드)

    사용법:
        with AudioListener() as listener:
            for frame in listener.frames():
                ...
    """

    def __init__(self, device: int | str | None = None) -> None:
        self.spec = resolve_stream_spec(device)
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=QUEUE_MAX_FRAMES)
        self._stream: sd.InputStream | None = None
        self.dropped_frames = 0   # 처리가 밀려서 버린 조각 수 (성능 문제 진단용)

    def _callback(self, indata, frames, time_info, status) -> None:
        """오디오 스레드에서 호출된다. 여기서는 절대 무거운 일을 하면 안 된다.

        오디오 콜백이 늦으면 소리가 끊기므로, 복사해서 큐에 넣기만 하고 즉시 반환한다.
        실제 계산은 메인 스레드(frames() 소비 쪽)에서 한다.
        """
        try:
            self._queue.put_nowait(indata.copy())
        except queue.Full:
            # 큐가 꽉 찼다 = 소비가 못 따라오고 있다.
            # 오래된 소리를 붙잡고 있어봐야 의미가 없으니 새 조각을 버리고 개수만 센다.
            self.dropped_frames += 1

    def __enter__(self) -> "AudioListener":
        try:
            self._stream = sd.InputStream(
                device=self.spec.device_index,
                samplerate=self.spec.sample_rate,
                channels=self.spec.channels,
                blocksize=self.spec.frame_size,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            raise AudioDeviceError(
                f"마이크를 열지 못했습니다: {exc}\n"
                "  - 다른 프로그램이 마이크를 독점 중인지 확인하세요.\n"
                "  - Windows 설정 > 개인 정보 및 보안 > 마이크 권한을 확인하세요.\n"
                "  - --list-devices 로 다른 장치를 골라볼 수도 있습니다."
            ) from exc
        return self

    def __exit__(self, *exc_info: object) -> None:
        """예외로 빠져나가도 스트림이 확실히 닫히도록 컨텍스트 매니저로 만든다."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def frames(self):
        """조각을 하나씩 내주는 제너레이터. 각 조각은 모노 float32 배열.

        스테레오로 열렸으면 채널을 평균 내서 모노로 합친다.
        (좌우 어느 쪽에서 박수가 나든 상관없으므로 방향 정보는 버린다.)
        """
        if self._stream is None:
            raise RuntimeError("with 문 안에서 사용하세요. (스트림이 열리지 않음)")

        while True:
            # timeout 을 두는 이유: 장치가 조용히 죽었을 때 영원히 멈춰 있지 않도록.
            try:
                block = self._queue.get(timeout=1.0)
            except queue.Empty:
                raise AudioDeviceError(
                    "1초 동안 마이크에서 데이터가 오지 않았습니다. "
                    "장치가 분리됐거나 다른 앱이 가져갔을 수 있습니다."
                ) from None

            yield block.mean(axis=1) if block.ndim > 1 else block
