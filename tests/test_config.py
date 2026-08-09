"""설정 파일 처리 테스트.

설정 오류는 사용자가 가장 자주 만나는 문제다. 죽더라도 '왜 죽었는지'가
메시지에 있어야 하므로, 에러 상황과 **메시지에 들어가야 할 단어**까지 테스트로 고정한다.

특히 신경 쓴 것:
  - 파일이 없을 때 "그럼 뭘 해야 하는지"(example 복사)가 메시지에 있는가
  - 문법 오류일 때 몇 번째 줄인지 알려주는가
  - 오타 난 항목을 조용히 무시하지 않는가 (설정을 바꿨는데 안 먹는 상황 방지)
"""

import pytest

from clap_launcher.config import (
    CONFIG_ENV_VAR,
    AppEntry,
    ConfigError,
    DetectionConfig,
    config_search_paths,
    find_config_path,
    load_config,
)


@pytest.fixture
def write_config(tmp_path, monkeypatch):
    """임시 폴더에 apps.yaml 을 써주고, 프로그램이 그걸 보게 만든다.

    진짜 내 설정 파일을 읽으면 기기마다 테스트 결과가 달라진다.
    """
    def _write(text: str):
        path = tmp_path / "apps.yaml"
        path.write_text(text, encoding="utf-8")
        monkeypatch.setenv(CONFIG_ENV_VAR, str(path))
        return path
    return _write


class TestFindConfig:
    def test_환경변수가_있으면_그것만_본다(self, tmp_path, monkeypatch):
        path = tmp_path / "somewhere.yaml"
        monkeypatch.setenv(CONFIG_ENV_VAR, str(path))
        assert config_search_paths() == [path]

    def test_기본_후보에_저장소의_config_폴더가_들어간다(self, monkeypatch):
        monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)
        candidates = config_search_paths()
        assert candidates[0].name == "apps.yaml"
        assert candidates[0].parent.name == "config"

    def test_파일이_하나도_없으면_None(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "없는파일.yaml"))
        assert find_config_path() is None


class TestMissingOrBroken:
    def test_파일이_없으면_예시_복사를_안내한다(self, tmp_path, monkeypatch):
        """⭐ 첫 실행에서 가장 흔한 상황이다. 여기서 막히면 아무것도 못 한다."""
        monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "없는파일.yaml"))
        with pytest.raises(ConfigError) as exc:
            load_config()
        message = str(exc.value)
        assert "apps.example.yaml" in message      # 무엇을 복사하면 되는지
        assert "없는파일.yaml" in message           # 어디를 찾아봤는지

    def test_exe로_받은_사람에게는_다른_안내를_한다(self, tmp_path, monkeypatch):
        """⭐ exe 하나만 받은 사람 옆에는 apps.example.yaml 이 없다.

        그 사람에게 '예시 파일을 복사하세요'라고 하면 없는 파일을 찾아 헤매게 된다.
        """
        import sys

        monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "없는파일.yaml"))
        monkeypatch.setattr(sys, "frozen", True, raising=False)

        with pytest.raises(ConfigError) as exc:
            load_config()

        message = str(exc.value)
        assert "프로그램 설정" in message           # 화면에서 등록하라고 안내
        assert "apps.example.yaml" not in message   # 없는 파일을 언급하지 않는다

    def test_문법이_깨지면_줄_번호를_알려준다(self, write_config):
        """⭐ 줄 번호가 없으면 사용자는 100줄짜리 파일을 눈으로 훑어야 한다."""
        write_config("apps:\n  - name: A\n   path: 어긋난들여쓰기\n")
        with pytest.raises(ConfigError) as exc:
            load_config()
        assert "3번째 줄" in str(exc.value)

    def test_최상위가_목록이면_거부한다(self, write_config):
        write_config("- name: A\n")
        with pytest.raises(ConfigError, match="최상위"):
            load_config()

    def test_빈_파일도_죽지_않는다(self, write_config):
        """주석만 남기고 다 지운 상태. 오류가 아니라 '등록된 게 없는' 상태다."""
        write_config("# 아직 아무것도 안 적었다\n")
        config = load_config()
        assert config.apps == []
        assert config.detection == DetectionConfig()   # 기본 기준값


class TestApps:
    def test_기본_항목을_읽는다(self, write_config):
        write_config("""
apps:
  - name: VS Code
    type: exe
    path: "C:/Program Files/Code.exe"
    args: ["F:/dev"]
    delay: 1.5
""")
        (app,) = load_config().apps
        assert app == AppEntry(name="VS Code", path="C:/Program Files/Code.exe",
                               type="exe", args=["F:/dev"], delay=1.5, enabled=True)

    def test_type을_생략하면_exe(self, write_config):
        write_config('apps:\n  - name: A\n    path: "C:/a.exe"\n')
        assert load_config().apps[0].type == "exe"

    def test_순서가_유지된다(self, write_config):
        """실행 순서가 곧 설정 파일의 순서다. 뒤바뀌면 delay 의미가 없어진다."""
        write_config("""
apps:
  - name: 첫째
    path: "a"
    type: url
  - name: 둘째
    path: "b"
    type: url
  - name: 셋째
    path: "c"
    type: url
""")
        assert [a.name for a in load_config().apps] == ["첫째", "둘째", "셋째"]

    def test_enabled_false_는_실행_대상에서_빠진다(self, write_config):
        write_config("""
apps:
  - name: 켠것
    path: "a"
    type: url
  - name: 꺼둔것
    path: "b"
    type: url
    enabled: false
""")
        config = load_config()
        assert len(config.apps) == 2                       # 목록에는 남아 있고
        assert [a.name for a in config.enabled_apps] == ["켠것"]   # 실행 대상에서만 빠진다

    def test_path가_없으면_몇_번째인지_알려준다(self, write_config):
        write_config('apps:\n  - name: A\n    path: "a"\n    type: url\n  - name: B\n')
        with pytest.raises(ConfigError) as exc:
            load_config()
        assert "'B'" in str(exc.value) and "path" in str(exc.value)

    def test_name이_없으면_몇_번째인지_알려준다(self, write_config):
        """이름이 없으면 '누구'라고 부를 수가 없으므로 순번으로 알려준다."""
        write_config('apps:\n  - path: "a"\n    type: url\n  - path: "b"\n    type: url\n')
        with pytest.raises(ConfigError) as exc:
            load_config()
        assert "1번째" in str(exc.value)

    def test_모르는_type은_쓸_수_있는_값을_알려준다(self, write_config):
        write_config('apps:\n  - name: A\n    path: "a"\n    type: shortcut\n')
        with pytest.raises(ConfigError) as exc:
            load_config()
        assert "shortcut" in str(exc.value)
        assert "folder" in str(exc.value)       # 대안 목록을 함께 보여준다

    def test_apps가_목록이_아니면_거부한다(self, write_config):
        write_config('apps:\n  name: A\n  path: "a"\n')
        with pytest.raises(ConfigError, match="목록"):
            load_config()

    def test_args를_문자열_하나로_적어도_받아준다(self, write_config):
        """흔한 실수라 굳이 죽이지 않는다. 의도가 명백하기 때문이다."""
        write_config('apps:\n  - name: A\n    path: "a"\n    type: url\n    args: "F:/dev"\n')
        assert load_config().apps[0].args == ["F:/dev"]

    def test_args의_숫자는_문자열로_바뀐다(self, write_config):
        """subprocess 는 문자열만 받는다. 여기서 안 바꾸면 실행 순간에 죽는다."""
        write_config('apps:\n  - name: A\n    path: "a"\n    type: url\n    args: [8080]\n')
        assert load_config().apps[0].args == ["8080"]

    @pytest.mark.parametrize("delay", ["빠르게", -1])
    def test_delay가_이상하면_거부한다(self, write_config, delay):
        write_config(f'apps:\n  - name: A\n    path: "a"\n    type: url\n    delay: {delay}\n')
        with pytest.raises(ConfigError, match="delay"):
            load_config()

    def test_enabled가_참거짓이_아니면_거부한다(self, write_config):
        write_config('apps:\n  - name: A\n    path: "a"\n    type: url\n    enabled: "no"\n')
        with pytest.raises(ConfigError, match="enabled"):
            load_config()


class TestDetection:
    def test_생략하면_기본값(self, write_config):
        write_config("apps: []\n")
        assert load_config().detection == DetectionConfig()

    def test_일부만_적으면_나머지는_기본값(self, write_config):
        write_config("detection:\n  max_harmonicity: 0.45\n")
        detection = load_config().detection
        assert detection.max_harmonicity == 0.45
        assert detection.onset_rise_db == DetectionConfig().onset_rise_db

    def test_오타난_항목을_조용히_넘기지_않는다(self, write_config):
        """⭐ 사람이 손으로 적는 파일이다. 무시하면 '왜 안 먹지'로 몇 시간을 날린다."""
        write_config("detection:\n  max_harmonicty: 0.45\n")   # i 빠짐
        with pytest.raises(ConfigError) as exc:
            load_config()
        assert "max_harmonicty" in str(exc.value)
        assert "max_harmonicity" in str(exc.value)   # 올바른 이름이 목록에 들어 있다

    def test_숫자가_아니면_거부한다(self, write_config):
        write_config('detection:\n  onset_rise_db: "높게"\n')
        with pytest.raises(ConfigError, match="숫자"):
            load_config()

    def test_음수를_거부한다(self, write_config):
        write_config("detection:\n  max_decay_ms: -10\n")
        with pytest.raises(ConfigError, match="0 이상"):
            load_config()

    def test_간격_항목은_정수가_된다(self, write_config):
        """ms 단위 간격은 정수로 다뤄진다. 실수로 적어도 받아준다."""
        write_config("detection:\n  min_interval_ms: 200.0\n")
        assert load_config().detection.min_interval_ms == 200

    @pytest.mark.parametrize("text", [
        "detection:\n  min_decay_ms: 80\n  max_decay_ms: 60\n",
        "detection:\n  min_flatness: 0.6\n  max_flatness: 0.5\n",
        "detection:\n  min_interval_ms: 900\n  max_interval_ms: 800\n",
    ])
    def test_하한이_상한보다_크면_거부한다(self, write_config, text):
        """⭐ 이 조합은 어떤 소리도 통과할 수 없다.

        그런데 화면에는 그냥 '걸러짐'으로만 찍혀서, 원인을 찾기가 정말 어렵다.
        설정을 읽는 시점에 막는 게 유일하게 친절한 방법이다.
        """
        write_config(text)
        with pytest.raises(ConfigError, match="통과하지 못해"):
            load_config()


class TestAudio:
    def test_비워두면_기본_장치(self, write_config):
        write_config("audio:\n  device:\n")
        assert load_config().audio.device is None

    def test_번호로_지정(self, write_config):
        write_config("audio:\n  device: 3\n")
        assert load_config().audio.device == 3

    def test_이름_일부로_지정(self, write_config):
        write_config('audio:\n  device: "Logitech"\n')
        assert load_config().audio.device == "Logitech"

    def test_참거짓은_거부한다(self, write_config):
        """device: true 를 1번 장치로 읽어버리면 엉뚱한 마이크가 열린다."""
        write_config("audio:\n  device: true\n")
        with pytest.raises(ConfigError, match="device"):
            load_config()


def test_저장소의_예시_파일은_항상_유효해야_한다():
    """⭐ 예시 파일이 깨져 있으면 새 사용자가 첫걸음에서 막힌다.

    (경로는 기기마다 다르므로 파일 위치를 직접 계산하지 않고 패키지 기준으로 찾는다)
    """
    from pathlib import Path

    import clap_launcher

    example = Path(clap_launcher.__file__).resolve().parents[2] / "config" / "apps.example.yaml"
    if not example.is_file():
        pytest.skip("예시 파일이 없는 환경(설치본 등)")

    config = load_config(example)
    assert config.apps, "예시 파일에는 앱이 최소 하나는 들어 있어야 한다"
    assert all(app.type in ("exe", "url", "folder", "store") for app in config.apps)
