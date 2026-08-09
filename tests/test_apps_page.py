"""프로그램 설정 화면 테스트.

이 화면은 사용자가 **자기 설정을 잃을 수 있는** 유일한 곳이다.
그래서 '고친 내용이 제대로 저장되는가'와 '실수로 날아가지 않는가'를 집중적으로 본다.

창을 띄우는 테스트지만 마이크는 쓰지 않는다(이 화면은 마이크와 무관하다).
"""

import pytest

from clap_launcher.config import CONFIG_ENV_VAR, AppEntry, DetectionConfig, load_config
from clap_launcher.ui.apps_page import (
    _first_problem,
    _format_delay,
    _parse_delay_text,
    _shorten,
)

# root(숨긴 Tk 창) 는 conftest.py 에 있다.

EXISTING_CONFIG = """
detection:
  max_harmonicity: 0.42
apps:
  - name: 첫째
    type: exe
    path: "C:/a.exe"
    delay: 1.5
  - name: 둘째
    type: url
    path: "https://b.com"
  - name: 꺼둔것
    type: folder
    path: "F:/dev"
    enabled: false
"""


@pytest.fixture
def make_page(root, tmp_path, monkeypatch):
    """임시 설정 파일을 깔고 편집 화면을 연다."""
    path = tmp_path / "apps.yaml"
    monkeypatch.setenv(CONFIG_ENV_VAR, str(path))
    made = []

    def _make(config_text: str | None = EXISTING_CONFIG):
        if config_text is not None:
            path.write_text(config_text, encoding="utf-8")

        from clap_launcher.ui.apps_page import AppsPage

        page = AppsPage(root, on_done=lambda: done.append(True))
        made.append(page)
        return page, path

    done: list[bool] = []
    _make.done = done
    yield _make
    for page in made:
        page.destroy()


class TestLoading:
    def test_기존_목록을_읽어온다(self, make_page):
        page, _path = make_page()
        assert [e.name for e in page.entries] == ["첫째", "둘째", "꺼둔것"]

    def test_설정_파일이_없어도_열린다(self, make_page):
        """⭐ 여기서 죽으면 설정을 고치러 온 사람이 설정을 고칠 수 없다."""
        page, _path = make_page(config_text=None)
        assert page.entries == []

    def test_깨진_파일이어도_열린다(self, make_page):
        page, _path = make_page("apps:\n  - name: 이름만\n")   # path 누락 = 읽기 실패
        assert page.entries == []

    def test_꺼둔_항목도_목록에_보인다(self, make_page):
        """지운 것과 꺼둔 것은 다르다. 목록에서 사라지면 지운 줄 안다."""
        page, _path = make_page()
        assert page.listbox.size() == 3
        assert "×" in page.listbox.get(2)


class TestEditing:
    def test_항목을_추가하면_맨_뒤에_붙고_선택된다(self, make_page):
        page, _path = make_page()
        page._add_entry()
        assert len(page.entries) == 4
        assert page.selected == 3

    def test_삭제하면_목록에서_빠진다(self, make_page, monkeypatch):
        monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **k: True)
        page, _path = make_page()
        page.selected = 1
        page._delete_entry()
        assert [e.name for e in page.entries] == ["첫째", "꺼둔것"]

    def test_삭제를_취소하면_그대로_남는다(self, make_page, monkeypatch):
        monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **k: False)
        page, _path = make_page()
        page.selected = 1
        page._delete_entry()
        assert len(page.entries) == 3

    def test_순서를_바꾸면_실행_순서가_바뀐다(self, make_page):
        page, _path = make_page()
        page.selected = 2
        page._move(-1)
        assert [e.name for e in page.entries] == ["첫째", "꺼둔것", "둘째"]
        assert page.selected == 1          # 고른 항목을 따라간다

    def test_순서를_바꾼_뒤_고치면_옮긴_항목이_고쳐진다(self, make_page):
        """⭐ 순서만 바꿨는데 그다음 타이핑이 옆 항목에 들어가면 안 된다.

        입력칸이 '몇 번째 항목'을 담고 있는지 따로 기억하지 않으면 실제로 이렇게 된다.
        """
        page, _path = make_page()
        page.listbox.selection_set(2)
        page._on_select()                  # '꺼둔것' 을 고른다
        page._move(-1)                     # 가운데로 올린다

        page.name_entry.delete(0, "end")
        page.name_entry.insert(0, "옮기고_고침")
        page._commit_form()

        assert [e.name for e in page.entries] == ["첫째", "옮기고_고침", "둘째"]

    def test_맨_위에서_더_올릴_수_없다(self, make_page):
        page, _path = make_page()
        page.selected = 0
        page._move(-1)
        assert [e.name for e in page.entries] == ["첫째", "둘째", "꺼둔것"]

    def test_켜고_끄기(self, make_page):
        page, _path = make_page()
        page.selected = 0
        page._toggle_enabled()
        assert page.entries[0].enabled is False
        page._toggle_enabled()
        assert page.entries[0].enabled is True


class TestForm:
    def test_고른_항목이_칸에_채워진다(self, make_page):
        page, _path = make_page()
        page.selected = 0
        page._fill_form()
        assert page.name_entry.get() == "첫째"
        assert page.path_entry.get() == "C:/a.exe"
        assert page.type_picker.value == "exe"
        assert page.delay_entry.get() == "1.5"

    def test_칸에_친_내용이_항목에_반영된다(self, make_page):
        page, _path = make_page()
        page.selected = 1
        page._fill_form()

        page.name_entry.delete(0, "end")
        page.name_entry.insert(0, "고친 이름")
        page._commit_form()

        assert page.entries[1].name == "고친 이름"

    def test_실행_인자는_빈칸으로_나뉜다(self, make_page):
        page, _path = make_page()
        page.selected = 0
        page._fill_form()
        page.args_entry.insert(0, "F:/dev --new-window")
        page._commit_form()
        assert page.entries[0].args == ["F:/dev", "--new-window"]

    def test_대기시간이_0이면_칸을_비워_둔다(self, make_page):
        """'0'이 적혀 있으면 뭔가 설정된 것처럼 보인다."""
        page, _path = make_page()
        page.selected = 1
        page._fill_form()
        assert page.delay_entry.get() == ""

    def test_다른_항목으로_옮겨도_고친_내용이_남는다(self, make_page):
        """⭐ 여기가 틀리면 방금 친 내용이 조용히 사라진다. 제일 화나는 버그다."""
        page, _path = make_page()
        page.selected = 0
        page._fill_form()
        page.name_entry.delete(0, "end")
        page.name_entry.insert(0, "바뀐첫째")

        page.listbox.selection_clear(0, "end")
        page.listbox.selection_set(1)
        page._on_select()                  # 목록에서 둘째를 고른 상황

        assert page.entries[0].name == "바뀐첫째"
        assert page.name_entry.get() == "둘째"


class TestSaving:
    def test_저장하면_파일에_반영되고_돌아간다(self, make_page):
        page, path = make_page()
        page.selected = 0
        page._fill_form()
        page.name_entry.delete(0, "end")
        page.name_entry.insert(0, "새이름")

        page._save()

        assert load_config(path).apps[0].name == "새이름"
        assert make_page.done == [True]          # 메인 화면으로 돌아갔다

    def test_감지_기준값을_건드리지_않는다(self, make_page):
        """⭐ 프로그램 목록만 고쳤는데 박수 보정 결과가 날아가면 안 된다."""
        page, path = make_page()
        page._save()
        assert load_config(path).detection.max_harmonicity == 0.42

    def test_경로가_비면_저장하지_않고_알려준다(self, make_page):
        page, path = make_page()
        page._add_entry()                        # 경로가 빈 새 항목
        page._save()

        assert make_page.done == []              # 화면을 벗어나지 않는다
        assert "경로" in page.status_label.cget("text")

    def test_취소하면_파일이_그대로다(self, make_page, monkeypatch):
        monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **k: True)
        page, path = make_page()
        before = path.read_text(encoding="utf-8")

        page._add_entry()
        page._cancel()

        assert path.read_text(encoding="utf-8") == before
        assert make_page.done == [True]

    def test_고친_게_있으면_취소할_때_물어본다(self, make_page, monkeypatch):
        """⭐ 실수로 눌러서 작업을 날리는 일이 없어야 한다."""
        asked = []
        monkeypatch.setattr("tkinter.messagebox.askyesno",
                            lambda *a, **k: asked.append(True) or False)
        page, _path = make_page()
        page._add_entry()

        page._cancel()

        assert asked == [True]
        assert make_page.done == []              # '아니오'를 골랐으니 그대로 머문다

    def test_고친_게_없으면_묻지_않고_돌아간다(self, make_page, monkeypatch):
        monkeypatch.setattr("tkinter.messagebox.askyesno",
                            lambda *a, **k: pytest.fail("묻지 말아야 한다"))
        page, _path = make_page()
        page._cancel()
        assert make_page.done == [True]


class TestHelpers:
    """창 없이도 검증할 수 있게 밖으로 뺀 계산들."""

    def test_짧은_경로는_그대로_둔다(self):
        assert _shorten("C:/a.exe") == "C:/a.exe"

    def test_긴_경로는_가운데를_접는다(self):
        long_path = "C:/Program Files/아주 긴 폴더 이름/그 안의 또 다른 폴더/app.exe"
        result = _shorten(long_path, limit=30)
        assert len(result) <= 30
        assert result.startswith("C:/Prog") and result.endswith("app.exe")

    @pytest.mark.parametrize("value,expected", [(0, ""), (0.0, ""), (1.5, "1.5"), (2.0, "2")])
    def test_대기시간_표시(self, value, expected):
        assert _format_delay(value) == expected

    @pytest.mark.parametrize("text,expected", [
        ("1.5", 1.5), ("2", 2.0), ("", 0.0), ("빠르게", 0.0), ("-3", 0.0), ("  0.5 ", 0.5),
    ])
    def test_대기시간_해석(self, text, expected):
        """⭐ 타이핑 도중('1.' 같은 상태)에 죽으면 글자를 칠 수가 없다."""
        assert _parse_delay_text(text) == expected

    def test_문제가_없으면_None(self):
        assert _first_problem([AppEntry(name="A", path="a", type="url")]) is None

    def test_이름이_없으면_몇_번째인지_알려준다(self):
        problem = _first_problem([AppEntry(name="  ", path="a", type="url")])
        assert "1번째" in problem

    def test_문제가_여럿이면_첫_번째만_알려준다(self):
        """한 번에 다 쏟아내면 어디부터 고칠지 알기 어렵다."""
        problem = _first_problem([
            AppEntry(name="A", path="", type="url"),
            AppEntry(name="B", path="", type="url"),
        ])
        assert "'A'" in problem and "'B'" not in problem


def test_기본_감지값은_건드리지_않는다():
    """DetectionConfig 기본값이 바뀌면 이 화면의 '보존' 테스트도 의미가 달라진다."""
    assert DetectionConfig().max_harmonicity != 0.42
