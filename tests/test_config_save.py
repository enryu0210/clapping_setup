"""설정 파일 저장 테스트.

⭐ 여기서 제일 중요한 것은 **되읽었을 때 같은 값이 나오는가**(왕복)다.
저장은 됐는데 다음 실행에서 못 읽으면, 사용자는 설정을 통째로 잃는다.

백업(.bak)도 테스트로 못 박아 둔다. 화면에서 저장하면 손으로 적어둔 주석이 사라지는데,
되돌릴 방법이 백업뿐이기 때문이다.
"""

import pytest
import yaml

from clap_launcher.config import (
    BACKUP_SUFFIX,
    CONFIG_ENV_VAR,
    AppEntry,
    AudioConfig,
    Config,
    DetectionConfig,
    Preset,
    dump_config_text,
    load_config,
    save_config,
)


def make_config(apps=None, claps: int = 2, presets=None, **detection_values) -> Config:
    """설정 하나를 만든다.

    apps 만 주면 그 목록을 claps(기본 2번) 프리셋에 담는다. 대부분의 테스트가
    '프리셋 하나'만 신경 쓰기 때문에 그 경우를 짧게 쓸 수 있게 해둔 것이다.
    """
    if presets is None:
        presets = [Preset(claps=claps, apps=apps if apps is not None else [])]
    return Config(
        detection=DetectionConfig(**detection_values),
        presets=presets,
        audio=AudioConfig(),
    )


def saved_apps(config: Config, claps: int = 2):
    """저장·되읽기 뒤 그 프리셋의 항목 목록. 테스트 본문을 짧게 유지하려고 뺐다."""
    return config.preset_at(claps).apps


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    """저장 위치를 임시 폴더로 돌린다. 진짜 내 apps.yaml 을 건드리면 안 된다."""
    path = tmp_path / "apps.yaml"
    monkeypatch.setenv(CONFIG_ENV_VAR, str(path))
    return path


class TestRoundTrip:
    def test_저장한_뒤_읽으면_같은_값이_나온다(self, config_path):
        """⭐ 이게 깨지면 사용자가 설정을 통째로 잃는다."""
        original = make_config([
            AppEntry(name="VS Code", path="C:/Program Files/Code.exe", type="exe",
                     args=["F:/dev"], delay=1.5),
            AppEntry(name="캘린더", path="https://calendar.google.com", type="url"),
            AppEntry(name="꺼둔것", path="F:/dev", type="folder", enabled=False),
        ])
        save_config(original, config_path)

        loaded = load_config(config_path)
        assert saved_apps(loaded) == saved_apps(original)

    def test_감지_기준값도_함께_보존된다(self, config_path):
        """⭐ 프로그램 목록을 고쳤다고 보정 결과가 날아가면 안 된다."""
        save_config(make_config(max_harmonicity=0.42, min_decay_ms=20.0), config_path)

        detection = load_config(config_path).detection
        assert detection.max_harmonicity == 0.42
        assert detection.min_decay_ms == 20.0

    def test_마이크_지정도_보존된다(self, config_path):
        config = make_config()
        config.audio = AudioConfig(device="Logitech")
        save_config(config, config_path)

        assert load_config(config_path).audio.device == "Logitech"

    def test_한글_이름이_깨지지_않는다(self, config_path):
        save_config(make_config([AppEntry(name="업무 브라우저", path="https://a.com",
                                          type="url")]), config_path)
        assert saved_apps(load_config(config_path))[0].name == "업무 브라우저"

    def test_빈_목록도_저장하고_읽을_수_있다(self, config_path):
        save_config(make_config([]), config_path)
        assert all(preset.is_empty for preset in load_config(config_path).presets)


class TestFileShape:
    def test_기본값인_항목은_적지_않는다(self):
        """파일이 짧아야 손으로 열어봤을 때 읽힌다."""
        text = dump_config_text(make_config([AppEntry(name="A", path="a", type="url")]))
        apps = yaml.safe_load(text)["presets"][0]["apps"]
        assert apps == [{"name": "A", "type": "url", "path": "a"}]   # args·delay·enabled 없음

    def test_기본값이_아닌_항목만_적는다(self):
        text = dump_config_text(make_config([
            AppEntry(name="A", path="a", type="exe", args=["x"], delay=2.0, enabled=False)]))
        app = yaml.safe_load(text)["presets"][0]["apps"][0]
        assert app["args"] == ["x"] and app["delay"] == 2.0 and app["enabled"] is False

    def test_주석이_사라진다는_경고가_파일에_남는다(self):
        """이 파일을 나중에 손으로 여는 사람에게도 알려줘야 한다."""
        text = dump_config_text(make_config())
        assert ".bak" in text
        assert "다시 작성" in text

    def test_순서가_유지된다(self):
        """목록 순서가 곧 실행 순서다. YAML이 이름순으로 정렬해버리면 안 된다."""
        text = dump_config_text(make_config([
            AppEntry(name="ㄴ둘째", path="b", type="url"),
            AppEntry(name="ㄱ첫째", path="a", type="url"),
        ]))
        assert ([a["name"] for a in yaml.safe_load(text)["presets"][0]["apps"]]
                == ["ㄴ둘째", "ㄱ첫째"])


class TestBackup:
    def test_덮어쓰기_전에_직전_파일을_남긴다(self, config_path):
        """⭐ 화면에서 저장하면 손으로 쓴 주석이 사라진다. 되돌릴 길은 이 백업뿐이다."""
        config_path.write_text("# 손으로 쓴 소중한 주석\napps: []\n", encoding="utf-8")

        save_config(make_config([AppEntry(name="A", path="a", type="url")]), config_path)

        backup = config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX)
        assert backup.is_file()
        assert "손으로 쓴 소중한 주석" in backup.read_text(encoding="utf-8")

    def test_처음_저장할_때는_백업이_없다(self, config_path):
        """백업할 것이 없는데 빈 파일을 만들어두면 헷갈린다."""
        save_config(make_config(), config_path)
        assert not config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX).exists()


class TestWhereToSave:
    def test_경로를_안_주면_지금_읽는_파일에_쓴다(self, config_path):
        config_path.write_text("apps: []\n", encoding="utf-8")

        written = save_config(make_config([AppEntry(name="A", path="a", type="url")]))

        assert written == config_path
        assert saved_apps(load_config(config_path))[0].name == "A"

    def test_파일이_없으면_첫_후보_위치에_새로_만든다(self, config_path):
        assert not config_path.exists()
        written = save_config(make_config())
        assert written == config_path and config_path.is_file()

    def test_폴더가_없어도_만들어서_저장한다(self, tmp_path, monkeypatch):
        """%LOCALAPPDATA%\\ClappingSetup 처럼 아직 없는 폴더로 물러설 수 있어야 한다."""
        target = tmp_path / "없던폴더" / "apps.yaml"
        monkeypatch.setenv(CONFIG_ENV_VAR, str(target))

        save_config(make_config())

        assert target.is_file()
