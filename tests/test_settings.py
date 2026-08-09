"""설정 저장/불러오기 테스트.

설정 파일은 사용자가 직접 손댈 일이 거의 없는 대신, 깨졌을 때 사용자가 스스로
고칠 방법도 없다. "깨져도 죽지 않고 기본값으로 시작한다"를 반드시 지켜야 해서
그 상황들을 테스트로 못 박아둔다.
"""

import json

import pytest

from clap_launcher.settings import (
    APP_DIR_NAME,
    LEGACY_APP_DIR_NAME,
    SETTINGS_ENV_VAR,
    Settings,
    legacy_settings_path,
    load_settings,
    save_settings,
    settings_path,
)


@pytest.fixture(autouse=True)
def temp_settings_file(tmp_path, monkeypatch):
    """테스트가 진짜 내 설정 파일을 건드리지 않도록 임시 경로로 바꿔치기한다."""
    path = tmp_path / "settings.json"
    monkeypatch.setenv(SETTINGS_ENV_VAR, str(path))
    return path


class TestSaveLoad:
    def test_저장한_값을_그대로_읽는다(self):
        save_settings(Settings(device=3, device_label="Mic In", setup_done=True))
        loaded = load_settings()
        assert (loaded.device, loaded.device_label, loaded.setup_done) == (3, "Mic In", True)

    def test_장치를_이름으로_저장할_수도_있다(self):
        """USB를 다시 꽂으면 번호가 바뀌므로 이름으로 저장하는 길도 열어둔다."""
        save_settings(Settings(device="Logitech", setup_done=True))
        assert load_settings().device == "Logitech"

    def test_한글_장치명이_깨지지_않는다(self):
        """'마이크(Realtek)' 처럼 한글 이름이 흔하다. 인코딩이 틀리면 여기서 깨진다."""
        save_settings(Settings(device=1, device_label="마이크(Realtek Audio)"))
        assert load_settings().device_label == "마이크(Realtek Audio)"

    def test_폴더가_없어도_알아서_만든다(self, tmp_path, monkeypatch):
        nested = tmp_path / "없는폴더" / "또없는폴더" / "settings.json"
        monkeypatch.setenv(SETTINGS_ENV_VAR, str(nested))
        save_settings(Settings(device=1))
        assert nested.exists()

    def test_임시파일_찌꺼기를_남기지_않는다(self, temp_settings_file):
        """원자적 저장에 쓴 .tmp 파일이 쌓이면 폴더가 지저분해진다."""
        save_settings(Settings(device=1))
        leftovers = list(temp_settings_file.parent.glob("*.tmp"))
        assert leftovers == []


class TestLoadFallback:
    def test_파일이_없으면_기본값(self):
        """첫 실행 상황. setup_done이 False라 마이크 선택 화면이 뜬다."""
        settings = load_settings()
        assert settings.setup_done is False
        assert settings.device is None

    def test_내용이_깨져도_죽지_않는다(self, temp_settings_file):
        temp_settings_file.write_text("{이건 JSON이 아님", encoding="utf-8")
        assert load_settings().setup_done is False

    def test_JSON이지만_형식이_다르면_기본값(self, temp_settings_file):
        """누군가 파일에 배열을 넣어놨어도 죽으면 안 된다."""
        temp_settings_file.write_text("[1, 2, 3]", encoding="utf-8")
        assert load_settings().setup_done is False

    def test_모르는_항목은_무시한다(self, temp_settings_file):
        """예전 버전이 남긴 설정 항목 때문에 프로그램이 죽으면 안 된다."""
        temp_settings_file.write_text(
            json.dumps({"device": 5, "옛날에쓰던항목": "값"}), encoding="utf-8"
        )
        assert load_settings().device == 5

    def test_빠진_항목은_기본값으로_채운다(self, temp_settings_file):
        temp_settings_file.write_text(json.dumps({"device": 5}), encoding="utf-8")
        settings = load_settings()
        assert settings.device == 5
        assert settings.setup_done is False


def test_환경변수가_없으면_사용자_폴더에_저장한다(monkeypatch):
    """실제 배포 상황: 쓰기 권한이 있는 사용자 폴더에 저장돼야 한다."""
    monkeypatch.delenv(SETTINGS_ENV_VAR, raising=False)
    path = settings_path()
    assert path.name == "settings.json"
    assert APP_DIR_NAME in str(path)


class TestLegacyMigration:
    """앱 이름을 ClappingSetup → ClapDesk 로 바꾸면서 기존 설정을 잃지 않아야 한다.

    ⭐ 여기가 틀리면 이름을 바꾼 순간 **마이크 선택과 박수 보정 결과가 통째로 사라진다.**
    사용자 입장에서는 업데이트했더니 처음부터 다시 설정하라는 화면이 뜨는 셈이다.
    """

    @pytest.fixture
    def fake_local_appdata(self, tmp_path, monkeypatch):
        """설정 폴더의 부모를 임시 폴더로 돌린다 (진짜 %LOCALAPPDATA% 를 안 건드리게)."""
        monkeypatch.delenv(SETTINGS_ENV_VAR, raising=False)
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        return tmp_path

    def _write_legacy(self, base, **values):
        legacy = base / LEGACY_APP_DIR_NAME / "settings.json"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        data = {"device": 3, "device_label": "Mic In", "setup_done": True,
                "detection": {"max_harmonicity": 0.42}}
        data.update(values)
        legacy.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return legacy

    def test_예전_설정을_읽어온다(self, fake_local_appdata):
        self._write_legacy(fake_local_appdata)

        settings = load_settings()

        assert settings.device == 3
        assert settings.setup_done is True
        assert settings.detection == {"max_harmonicity": 0.42}   # 보정 결과가 살아남는다

    def test_읽어온_뒤_새_위치에_옮겨_적는다(self, fake_local_appdata):
        """다음 실행부터는 예전 폴더를 보지 않아도 되게."""
        self._write_legacy(fake_local_appdata)

        load_settings()

        assert (fake_local_appdata / APP_DIR_NAME / "settings.json").is_file()

    def test_예전_파일을_지우지_않는다(self, fake_local_appdata):
        """옮기다 잘못돼도 되돌릴 곳이 있어야 한다. 용량도 1KB 남짓이다."""
        legacy = self._write_legacy(fake_local_appdata)
        load_settings()
        assert legacy.is_file()

    def test_새_설정이_있으면_예전_것을_보지_않는다(self, fake_local_appdata):
        """⭐ 이미 새 이름으로 쓰던 사람의 설정을 예전 값으로 덮으면 안 된다."""
        self._write_legacy(fake_local_appdata, device=3, device_label="예전 마이크")
        save_settings(Settings(device=7, device_label="지금 마이크", setup_done=True))

        assert load_settings().device == 7

    def test_예전_것도_없으면_기본값(self, fake_local_appdata):
        assert load_settings() == Settings()

    def test_예전_파일이_깨져_있어도_죽지_않는다(self, fake_local_appdata):
        legacy = fake_local_appdata / LEGACY_APP_DIR_NAME / "settings.json"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text("{망가진 json", encoding="utf-8")

        assert load_settings() == Settings()

    def test_환경변수를_쓰면_예전_폴더를_찾지_않는다(self, tmp_path, monkeypatch):
        """테스트가 남의 기기에 있는 진짜 설정을 읽어오면 결과가 기기마다 달라진다."""
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        monkeypatch.setenv(SETTINGS_ENV_VAR, str(tmp_path / "따로.json"))
        self._write_legacy(tmp_path)

        assert legacy_settings_path() is None
        assert load_settings() == Settings()
