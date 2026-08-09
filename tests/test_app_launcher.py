"""프로그램 실행 테스트.

⚠️ 진짜로 프로그램을 켜는 테스트는 만들지 않는다. 테스트를 한 번 돌릴 때마다
   VS Code 8개가 열리면 아무도 테스트를 안 돌리게 된다.
   그래서 '무엇을 어떤 순서로 실행하려 했는지'만 가짜 실행기로 확인한다.

여기서 반드시 지켜야 하는 것:
  ⭐ 하나가 실패해도 나머지는 전부 실행된다 (이게 이 모듈의 존재 이유다)
  ⭐ 실패 이유가 결과에 남는다 (사용자가 고칠 수 있어야 한다)
"""

import pytest

from clap_launcher.config import AppEntry
from clap_launcher.launcher.app_launcher import (
    AppLauncher,
    LaunchError,
    LaunchResult,
    launch_exe,
    launch_folder,
    launch_url,
)


class FakeLaunchers:
    """실행한 척만 하고 기록을 남기는 가짜 실행기 묶음.

    fail_names 에 든 이름은 실패시킨다 — '하나 실패해도 나머지는 켜진다'를 확인하기 위함.
    """

    def __init__(self, fail_names: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []      # (type, name) 실행한 순서대로
        self.fail_names = fail_names or set()

    def _make(self, app_type: str):
        def _run(entry: AppEntry) -> None:
            self.calls.append((app_type, entry.name))
            if entry.name in self.fail_names:
                raise LaunchError("일부러 실패시킴")
        return _run

    def as_dict(self) -> dict:
        return {t: self._make(t) for t in ("exe", "url", "folder", "store")}


def entry(name: str, app_type: str = "url", **kwargs) -> AppEntry:
    """테스트용 항목 하나. path 는 어차피 가짜 실행기가 안 보므로 아무 값이나 준다."""
    return AppEntry(name=name, path=f"//{name}", type=app_type, **kwargs)


class TestLaunchAll:
    def test_목록_순서대로_실행한다(self):
        fake = FakeLaunchers()
        launcher = AppLauncher(launchers=fake.as_dict(), sleep=lambda _: None)

        result = launcher.launch_all([entry("첫째"), entry("둘째"), entry("셋째")])

        assert [name for _type, name in fake.calls] == ["첫째", "둘째", "셋째"]
        assert result.succeeded == ["첫째", "둘째", "셋째"]
        assert result.ok

    def test_type에_맞는_실행기를_고른다(self):
        fake = FakeLaunchers()
        AppLauncher(launchers=fake.as_dict()).launch_all([
            entry("프로그램", "exe"), entry("사이트", "url"),
            entry("폴더", "folder"), entry("스토어앱", "store"),
        ])
        assert [t for t, _name in fake.calls] == ["exe", "url", "folder", "store"]

    def test_하나가_실패해도_나머지는_전부_실행된다(self):
        """⭐ 이 모듈의 존재 이유. 경로 오타 하나로 아침 준비가 통째로 날아가면 안 된다."""
        fake = FakeLaunchers(fail_names={"둘째"})
        launcher = AppLauncher(launchers=fake.as_dict())

        result = launcher.launch_all([entry("첫째"), entry("둘째"), entry("셋째")])

        assert [name for _t, name in fake.calls] == ["첫째", "둘째", "셋째"]  # 셋 다 시도했다
        assert result.succeeded == ["첫째", "셋째"]
        assert result.failed == [("둘째", "일부러 실패시킴")]
        assert not result.ok

    def test_예상_못_한_오류도_나머지를_막지_않는다(self):
        """LaunchError 가 아닌 오류(라이브러리 버그 등)에도 같은 원칙이 지켜져야 한다."""
        def 폭발(_entry):
            raise RuntimeError("예기치 못한 무언가")

        launchers = {**FakeLaunchers().as_dict(), "exe": 폭발}
        result = AppLauncher(launchers=launchers).launch_all(
            [entry("터지는것", "exe"), entry("멀쩡한것", "url")])

        assert result.succeeded == ["멀쩡한것"]
        assert "예기치 못한 무언가" in result.failed[0][1]

    def test_모르는_type은_실패로_기록된다(self):
        """설정 검사를 우회해서 들어온 경우에도 죽지 않아야 한다."""
        result = AppLauncher(launchers={}).launch_all([entry("이상한것", "exe")])
        assert result.failed == [("이상한것", "모르는 type 입니다: exe")]

    def test_꺼둔_항목은_실행하지_않는다(self):
        fake = FakeLaunchers()
        result = AppLauncher(launchers=fake.as_dict()).launch_all(
            [entry("켠것"), entry("꺼둔것", enabled=False)])

        assert [name for _t, name in fake.calls] == ["켠것"]
        assert result.skipped == 1

    def test_빈_목록도_죽지_않는다(self):
        result = AppLauncher(launchers={}).launch_all([])
        assert result.succeeded == [] and result.failed == []


class TestDelay:
    def test_delay_만큼_쉬어간다(self):
        slept = []
        fake = FakeLaunchers()
        launcher = AppLauncher(launchers=fake.as_dict(), sleep=slept.append)

        launcher.launch_all([entry("무거운앱", delay=1.5), entry("가벼운앱"), entry("마지막")])

        assert slept == [1.5]

    def test_마지막_항목_뒤에는_기다리지_않는다(self):
        """⭐ 마지막에 기다려봐야 화면 복귀만 늦어진다. 기다릴 다음 항목이 없다."""
        slept = []
        launcher = AppLauncher(launchers=FakeLaunchers().as_dict(), sleep=slept.append)

        launcher.launch_all([entry("혼자", delay=3.0)])

        assert slept == []

    def test_실패한_항목의_delay도_지킨다(self):
        """실패했어도 시스템이 바쁜 건 마찬가지다. 여기서 몰아치면 PC가 버벅인다."""
        slept = []
        fake = FakeLaunchers(fail_names={"실패할것"})
        launcher = AppLauncher(launchers=fake.as_dict(), sleep=slept.append)

        launcher.launch_all([entry("실패할것", delay=0.5), entry("다음것")])

        assert slept == [0.5]

    def test_꺼둔_항목의_delay는_무시한다(self):
        """실행하지도 않은 항목 때문에 기다리는 건 낭비다."""
        slept = []
        launcher = AppLauncher(launchers=FakeLaunchers().as_dict(), sleep=slept.append)

        launcher.launch_all([entry("꺼둔것", delay=2.0, enabled=False), entry("켠것")])

        assert slept == []


class TestSummary:
    def test_전부_성공하면_개수만(self):
        assert LaunchResult(succeeded=["A", "B"]).summary() == "성공 2개"

    def test_실패하면_이름과_이유를_함께_보여준다(self):
        """⭐ '1개 실패'만 알려주면 무엇을 고쳐야 할지 알 수 없다."""
        summary = LaunchResult(succeeded=["A"], failed=[("Slack", "경로를 찾을 수 없습니다")]).summary()
        assert "성공 1개" in summary
        assert "실패 1개" in summary
        assert "Slack: 경로를 찾을 수 없습니다" in summary

    def test_꺼둔_항목_개수도_알려준다(self):
        assert "꺼둔 항목 2개" in LaunchResult(succeeded=["A"], skipped=2).summary()

    def test_아무것도_없으면_그렇다고_말한다(self):
        assert LaunchResult().summary() == "실행할 프로그램이 없습니다."


class TestRealLaunchers:
    """실제 실행 함수들 — 실행이 아니라 '실행 전 검사'만 확인한다.

    경로가 틀렸을 때 어떤 메시지가 나오는지가 사용자에게는 가장 중요하다.
    """

    def test_없는_경로는_친절한_메시지로_실패한다(self, tmp_path):
        target = tmp_path / "없는프로그램.exe"
        with pytest.raises(LaunchError) as exc:
            launch_exe(AppEntry(name="A", path=str(target)))
        assert "경로를 찾을 수 없습니다" in str(exc.value)
        assert str(target) in str(exc.value)      # 어떤 경로가 문제인지 그대로 보여준다

    def test_폴더를_exe로_적으면_고칠_방법을_알려준다(self, tmp_path):
        """흔한 실수다. 그냥 '실행 실패'라고 하면 원인을 짐작할 수 없다."""
        with pytest.raises(LaunchError, match="folder"):
            launch_exe(AppEntry(name="A", path=str(tmp_path)))

    def test_없는_폴더도_친절한_메시지로_실패한다(self, tmp_path):
        with pytest.raises(LaunchError, match="폴더를 찾을 수 없습니다"):
            launch_folder(AppEntry(name="A", path=str(tmp_path / "없음"), type="folder"))

    def test_주소에_http가_없으면_붙여준다(self, monkeypatch):
        """'github.com' 만 적으면 브라우저가 파일 경로로 오해한다. 흔한 실수라 보정한다."""
        opened = []
        monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)

        launch_url(AppEntry(name="A", path="github.com", type="url"))

        assert opened == ["https://github.com"]

    def test_이미_있는_주소는_건드리지_않는다(self, monkeypatch):
        opened = []
        monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)

        launch_url(AppEntry(name="A", path="http://localhost:8080", type="url"))

        assert opened == ["http://localhost:8080"]

    def test_브라우저를_못_열면_실패로_알린다(self, monkeypatch):
        monkeypatch.setattr("webbrowser.open", lambda url: False)
        with pytest.raises(LaunchError, match="브라우저"):
            launch_url(AppEntry(name="A", path="https://example.com", type="url"))
