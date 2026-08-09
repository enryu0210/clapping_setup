"""프로그램 설정 화면 — 박수 치면 실행할 목록을 편집한다.

이 화면이 없던 시절에는 `config/apps.yaml` 을 메모장으로 열어 고쳐야 했다.
경로에 역슬래시를 잘못 쓰거나 들여쓰기가 어긋나면 프로그램이 뜨지 않았고,
그때마다 원인을 찾는 게 일이었다. 그래서 **파일을 몰라도 쓸 수 있게** 화면을 붙였다.

⚠️ 저장하면 apps.yaml 이 다시 작성된다(주석이 사라진다).
   그 대신 직전 파일이 apps.yaml.bak 으로 남는다. 자세한 배경은 config.py 의 '저장' 부분.

화면 구성:
  위  — 등록된 항목 목록 (순서 = 실행 순서)
  가운데 — 목록을 다루는 버튼들 (추가·삭제·순서·켜고 끄기)
  아래 — 고른 항목 하나를 고치는 입력칸들
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..config import (
    VALID_APP_TYPES,
    AppEntry,
    AudioConfig,
    Config,
    ConfigError,
    DetectionConfig,
    find_config_path,
    load_config,
    save_config,
)
from . import icons, theme
from .neumorphic import NeoButton, NeoPanel, NeoSegmented

PANEL_WIDTH = 520

# 화면에 보여줄 이름 ↔ 파일에 적히는 값.
# 이름을 짧게 둔 이유: 네 개가 한 줄에 들어가야 하는데, 길면 마지막 칸이 잘린다.
TYPE_OPTIONS = [("프로그램", "exe"), ("웹주소", "url"), ("폴더", "folder"), ("스토어", "store")]
TYPE_LABELS = dict((value, label) for label, value in TYPE_OPTIONS)

# 종류별로 경로 칸에 무엇을 적어야 하는지 알려주는 안내문
PATH_HINTS = {
    "exe": "실행파일 경로 — 예: C:/Program Files/Microsoft VS Code/Code.exe",
    "url": "웹 주소 — 예: https://github.com  (http를 빼먹어도 붙여줍니다)",
    "folder": "폴더 경로 — 예: F:/dev",
    "store": "스토어 앱 ID — 'Win+R → shell:AppsFolder' 에서 확인 (docs/CONFIG.md 3장)",
}


class AppsPage(ttk.Frame):
    """실행할 프로그램 목록 편집 화면."""

    def __init__(self, parent, on_done) -> None:
        """
        Args:
            on_done: 편집을 끝내고 메인 화면으로 돌아갈 때 부를 함수
        """
        super().__init__(parent, padding=(theme.px(24), theme.px(18)))
        self.on_done = on_done

        self.entries: list[AppEntry] = []
        self.selected: int | None = None
        self._dirty = False          # 저장하지 않은 변경이 있는가
        self._filling_form = False   # 화면이 칸을 채우는 중 (사용자 입력과 구분하기 위함)
        # ⚠️ 입력칸이 **지금 어느 항목의 내용을 담고 있는지**를 따로 기억한다.
        #    selected 만 보고 저장하면, 선택이 먼저 바뀐 상황에서 엉뚱한 항목을
        #    덮어쓴다(테스트로 실제 재현됨). 칸을 채운 순간의 번호가 정답이다.
        self._form_index: int | None = None

        # apps 외의 설정(마이크·감지 기준값)은 건드리지 않고 그대로 다시 저장해야 한다.
        # 이걸 빠뜨리면 프로그램 목록을 고칠 때마다 보정값이 초기화된다.
        self._detection = DetectionConfig()
        self._audio = AudioConfig()

        self._load_existing()
        self._build()
        self._refresh_list()
        self._fill_form()

    # ── 파일 읽기 ──────────────────────────────────────────
    def _load_existing(self) -> None:
        """지금 설정을 읽어온다. 파일이 없거나 깨져 있어도 빈 목록으로 시작한다.

        여기서 죽으면 **설정을 고치러 온 사람이 설정을 고칠 수 없다.** 그게 제일 나쁘다.
        """
        try:
            config = load_config()
        except ConfigError:
            return          # 파일이 없는 첫 사용 — 빈 목록에서 시작하면 된다
        self.entries = list(config.apps)
        self._detection = config.detection
        self._audio = config.audio

    # ── 화면 구성 ──────────────────────────────────────────
    def _build(self) -> None:
        header = tk.Canvas(self, width=theme.px(PANEL_WIDTH), height=theme.px(40),
                           bg=theme.BG, highlightthickness=0, bd=0)
        header.pack(anchor="w")
        icons.draw(header, "list", theme.px(16), theme.px(20), theme.px(26),
                   theme.ACCENT, width=2)
        header.create_text(theme.px(38), theme.px(21), text="박수 치면 실행할 프로그램",
                           anchor="w", fill=theme.FG, font=theme.FONT_TITLE)

        ttk.Label(self, text="위에서 아래 순서대로 실행됩니다. 항목을 골라 아래에서 고치세요.",
                  style="Muted.TLabel").pack(anchor="w", pady=(theme.px(4), theme.px(8)))

        self._build_list()
        self._build_list_buttons()
        self._build_form()
        self._build_footer()

    def _build_list(self) -> None:
        panel = NeoPanel(self, width=PANEL_WIDTH, height=126, padding=10)
        panel.pack(anchor="w")

        scrollbar = ttk.Scrollbar(panel.body, orient="vertical")
        self.listbox = tk.Listbox(
            panel.body, activestyle="none", exportselection=False,
            bg=theme.BG_SUNKEN, fg=theme.FG, selectbackground=theme.ACCENT,
            selectforeground=theme.FG_ON_ACCENT, highlightthickness=0, bd=0,
            font=theme.FONT_BODY, yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self.listbox.yview)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

    def _build_list_buttons(self) -> None:
        row = ttk.Frame(self)
        row.pack(anchor="w", pady=(theme.px(2), 0))
        NeoButton(row, text="추가", icon="plus", command=self._add_entry,
                  height=32).pack(side="left")
        self.delete_button = NeoButton(row, text="삭제", icon="trash",
                                       command=self._delete_entry, height=32)
        self.delete_button.pack(side="left")
        self.up_button = NeoButton(row, text="", icon="arrow_up", width=42,
                                   command=lambda: self._move(-1), height=32)
        self.up_button.pack(side="left")
        self.down_button = NeoButton(row, text="", icon="arrow_down", width=42,
                                     command=lambda: self._move(1), height=32)
        self.down_button.pack(side="left")
        self.toggle_button = NeoButton(row, text="켜기/끄기", icon="check",
                                       command=self._toggle_enabled, height=32)
        self.toggle_button.pack(side="left")

    def _build_form(self) -> None:
        """고른 항목 하나를 고치는 칸들."""
        form = ttk.Frame(self)
        form.pack(anchor="w", fill="x", pady=(theme.px(6), 0))
        form.columnconfigure(1, weight=1)

        self.name_entry = self._add_field(form, 0, "이름")
        self.name_entry.bind("<KeyRelease>", self._on_form_change)

        ttk.Label(form, text="종류", style="Small.TLabel").grid(
            row=1, column=0, sticky="w", pady=theme.px(3))
        self.type_picker = NeoSegmented(form, options=TYPE_OPTIONS, value="exe",
                                        command=self._on_type_change)
        # 칸 두 개를 걸쳐 놓는다. 한 칸 안에 두면 마지막 '스토어'가 잘린다.
        self.type_picker.grid(row=1, column=1, columnspan=2, sticky="w")

        self.path_entry = self._add_field(form, 2, "경로")
        self.path_entry.bind("<KeyRelease>", self._on_form_change)
        self.browse_button = NeoButton(form, text="찾아보기", icon="folder",
                                       command=self._browse, height=30)
        self.browse_button.grid(row=2, column=2, sticky="w")

        self.hint_label = ttk.Label(form, text="", style="Small.TLabel",
                                    wraplength=theme.px(PANEL_WIDTH))
        self.hint_label.grid(row=3, column=1, columnspan=2, sticky="w")

        self.args_entry = self._add_field(form, 4, "실행 인자")
        self.args_entry.bind("<KeyRelease>", self._on_form_change)
        ttk.Label(form, text="여러 개면 빈칸으로 구분 (예: 열 폴더, 열 주소)",
                  style="Small.TLabel").grid(row=5, column=1, sticky="w")

        self.delay_entry = self._add_field(form, 6, "대기(초)", width=8, stretch=False)
        self.delay_entry.bind("<KeyRelease>", self._on_form_change)
        ttk.Label(form, text="이 항목을 켠 뒤 다음 항목까지 쉬는 시간 (무거운 프로그램 뒤에 1~2초)",
                  style="Small.TLabel").grid(row=7, column=1, columnspan=2, sticky="w")

    def _add_field(self, parent, row: int, label: str, width: int = 46,
                   stretch: bool = True) -> ttk.Entry:
        """'라벨 + 입력칸' 한 줄. 같은 모양이 여러 번 나와서 함수로 묶었다.

        Args:
            stretch: 칸을 가로로 늘릴지. 대기 시간처럼 숫자 몇 자만 넣는 칸은
                     늘리면 오히려 '뭔가 길게 적어야 하나' 싶어진다.
        """
        ttk.Label(parent, text=label, style="Small.TLabel").grid(
            row=row, column=0, sticky="w", padx=(0, theme.px(8)), pady=theme.px(3))
        entry = ttk.Entry(parent, style="Neo.TEntry", width=width, font=theme.FONT_BODY)
        entry.grid(row=row, column=1, sticky="we" if stretch else "w", pady=theme.px(3))
        return entry

    def _build_footer(self) -> None:
        row = ttk.Frame(self)
        row.pack(anchor="w", pady=(theme.px(6), 0))
        NeoButton(row, text="저장하고 돌아가기", icon="check", accent=True,
                  command=self._save).pack(side="left")
        NeoButton(row, text="취소", icon="close", command=self._cancel).pack(side="left")

        self.status_label = ttk.Label(self, text="", style="Small.TLabel",
                                      wraplength=theme.px(PANEL_WIDTH), justify="left")
        self.status_label.pack(anchor="w", pady=(theme.px(6), 0))
        self._show_file_hint()

    def _show_file_hint(self) -> None:
        """어느 파일을 고치게 되는지 알려준다. 저장이 어디로 가는지 모르면 불안하다."""
        path = find_config_path()
        # 경로가 길면 줄바꿈이 늘어나 아래 안내가 창 밖으로 밀린다. 가운데를 접어서 보여준다.
        where = _shorten(str(path), 66) if path else "config/apps.yaml (새로 만듭니다)"
        self._set_status(f"저장 위치: {where}\n"
                         "저장하면 이 파일을 다시 씁니다 (직전 내용은 .bak 으로 보관).",
                         theme.FG_MUTED)

    def _set_status(self, text: str, color: str = theme.FG_MUTED) -> None:
        self.status_label.config(text=text, foreground=color)

    # ── 목록 ───────────────────────────────────────────────
    def _refresh_list(self) -> None:
        """목록을 다시 그린다. 고른 항목은 그대로 유지한다."""
        self.listbox.delete(0, tk.END)
        for entry in self.entries:
            mark = "○" if entry.enabled else "×"
            kind = TYPE_LABELS.get(entry.type, entry.type)
            self.listbox.insert(tk.END, f" {mark} {entry.name}   [{kind}]   "
                                        f"{_shorten(entry.path)}")
            if not entry.enabled:
                # 꺼둔 항목은 흐리게 — 지운 것과 헷갈리지 않게 한다
                self.listbox.itemconfig(tk.END, foreground=theme.FG_MUTED)

        if self.selected is not None and 0 <= self.selected < len(self.entries):
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(self.selected)
            self.listbox.see(self.selected)
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        """고른 항목이 없으면 못 누르게 한다. 눌렀는데 아무 일도 안 나는 것보다 낫다."""
        has = self.selected is not None
        for button in (self.delete_button, self.toggle_button, self.browse_button):
            button.configure_state(has)
        self.up_button.configure_state(has and self.selected > 0)
        self.down_button.configure_state(has and self.selected < len(self.entries) - 1)

    def _on_select(self, _event=None) -> None:
        """목록에서 다른 항목을 골랐을 때. 먼저 지금 칸의 내용을 저장하고 넘어간다."""
        selection = self.listbox.curselection()
        if not selection:
            return
        self._commit_form()
        self.selected = selection[0]
        self._fill_form()
        self._refresh_buttons()

    # ── 항목 다루기 ────────────────────────────────────────
    def _add_entry(self) -> None:
        self._commit_form()
        self.entries.append(AppEntry(name="새 항목", path="", type="exe"))
        self.selected = len(self.entries) - 1
        self._mark_dirty()
        self._refresh_list()
        self._fill_form()
        self.name_entry.focus_set()
        self.name_entry.selection_range(0, tk.END)   # 바로 이름을 덮어쓸 수 있게

    def _delete_entry(self) -> None:
        if self.selected is None:
            return
        name = self.entries[self.selected].name
        if not messagebox.askyesno("삭제", f"'{name}' 항목을 지울까요?", parent=self):
            return
        del self.entries[self.selected]
        # 마지막 항목을 지웠으면 그 앞 항목을 고른 상태로 둔다
        self.selected = min(self.selected, len(self.entries) - 1) if self.entries else None
        self._mark_dirty()
        self._refresh_list()
        self._fill_form()

    def _move(self, step: int) -> None:
        """순서 바꾸기. 목록 순서가 곧 실행 순서다."""
        if self.selected is None:
            return
        target = self.selected + step
        if not 0 <= target < len(self.entries):
            return
        self._commit_form()
        entries = self.entries
        entries[self.selected], entries[target] = entries[target], entries[self.selected]
        self.selected = target
        self._mark_dirty()
        self._refresh_list()
        # 항목이 자리를 옮겼으니 칸이 가리키는 번호도 새로 맞춰야 한다.
        # 안 그러면 그다음에 친 글자가 옆 항목에 들어간다.
        self._fill_form()

    def _toggle_enabled(self) -> None:
        """지우지 않고 잠시 끄기."""
        if self.selected is None:
            return
        entry = self.entries[self.selected]
        entry.enabled = not entry.enabled
        self._mark_dirty()
        self._refresh_list()

    # ── 입력칸 ↔ 항목 ──────────────────────────────────────
    def _fill_form(self) -> None:
        """고른 항목의 값을 칸에 채운다."""
        self._filling_form = True     # 이 동안의 변경은 사용자가 친 게 아니다
        try:
            entry = (self.entries[self.selected]
                     if self.selected is not None and self.entries else None)
            for widget, value in (
                (self.name_entry, entry.name if entry else ""),
                (self.path_entry, entry.path if entry else ""),
                (self.args_entry, " ".join(entry.args) if entry else ""),
                (self.delay_entry, _format_delay(entry.delay) if entry else ""),
            ):
                widget.delete(0, tk.END)
                widget.insert(0, value)
            self.type_picker.set(entry.type if entry else "exe")
            self._form_index = self.selected if entry else None
            self._update_hint()
        finally:
            self._filling_form = False

    def _commit_form(self) -> None:
        """칸에 적힌 내용을 **그 칸이 보여주던 항목**에 반영한다.

        항목을 바꾸거나 저장하기 **전에** 반드시 불러야 한다.
        안 그러면 방금 친 내용이 조용히 사라진다.
        """
        index = self._form_index
        if index is None or not 0 <= index < len(self.entries):
            return
        entry = self.entries[index]
        entry.name = self.name_entry.get().strip() or "이름 없음"
        entry.path = self.path_entry.get().strip()
        entry.type = self.type_picker.value
        entry.args = self.args_entry.get().split()
        entry.delay = _parse_delay_text(self.delay_entry.get())

    def _on_form_change(self, _event=None) -> None:
        if self._filling_form:
            return
        self._commit_form()
        self._mark_dirty()
        self._refresh_list()      # 목록에도 바뀐 이름·경로가 바로 보이게

    def _on_type_change(self) -> None:
        self._on_form_change()
        self._update_hint()

    def _update_hint(self) -> None:
        """종류에 따라 경로 칸 안내문과 '찾아보기' 버튼 사용 여부를 바꾼다."""
        kind = self.type_picker.value
        self.hint_label.config(text=PATH_HINTS.get(kind, ""))
        # url·store 는 파일 탐색기로 고를 수 있는 대상이 아니다
        self.browse_button.configure_state(self.selected is not None
                                           and kind in ("exe", "folder"))

    def _browse(self) -> None:
        """파일 탐색기로 경로를 고른다. 손으로 치다 생기는 오타를 줄이는 게 목적이다."""
        kind = self.type_picker.value
        if kind == "folder":
            chosen = filedialog.askdirectory(title="폴더 고르기", parent=self)
        else:
            chosen = filedialog.askopenfilename(
                title="실행파일 고르기", parent=self,
                filetypes=[("실행파일", "*.exe"), ("모든 파일", "*.*")])
        if not chosen:
            return                       # 사용자가 취소했다

        # YAML·Windows 양쪽에서 안전하도록 슬래시로 통일한다 (역슬래시는 문제를 일으킨다)
        self.path_entry.delete(0, tk.END)
        self.path_entry.insert(0, chosen.replace("\\", "/"))
        self._on_form_change()

    # ── 저장 / 취소 ────────────────────────────────────────
    def _mark_dirty(self) -> None:
        self._dirty = True

    def _save(self) -> None:
        self._commit_form()

        problem = _first_problem(self.entries)
        if problem is not None:
            self._set_status(f"⚠ {problem}", theme.ERROR)
            return

        config = Config(detection=self._detection, apps=self.entries, audio=self._audio)
        try:
            path = save_config(config)
        except (ConfigError, OSError) as exc:
            self._set_status(f"⚠ 저장하지 못했습니다: {exc}", theme.ERROR)
            return

        self._dirty = False
        print(f"설정을 저장했습니다: {path}")   # 콘솔에도 남겨 두면 문제 추적이 쉽다
        self.on_done()

    def _cancel(self) -> None:
        """고치던 것을 버리고 돌아간다. 실수로 날리는 일이 없게 한 번 물어본다."""
        self._commit_form()
        if self._dirty and not messagebox.askyesno(
                "취소", "저장하지 않은 변경이 있습니다. 버리고 돌아갈까요?", parent=self):
            return
        self.on_done()


# ── 화면과 상관없는 계산들 (창 없이 테스트할 수 있게 밖으로 뺐다) ──

def _shorten(path: str, limit: int = 42) -> str:
    """긴 경로를 가운데를 접어서 줄인다. 앞(드라이브)과 뒤(파일명)가 제일 중요하다."""
    if len(path) <= limit:
        return path
    keep = (limit - 3) // 2
    return f"{path[:keep]}…{path[-keep:]}"


def _format_delay(delay: float) -> str:
    """0이면 빈칸으로 둔다. '0'이 적혀 있으면 뭔가 설정된 것처럼 보인다."""
    if not delay:
        return ""
    return f"{delay:g}"


def _parse_delay_text(text: str) -> float:
    """대기 시간 칸의 글자를 숫자로. 이상한 값은 0으로 본다.

    타이핑 도중('1.' 같은 상태)에도 오류를 띄우면 글자를 칠 수가 없다.
    저장할 때 다시 검사하므로 여기서는 조용히 넘어간다.
    """
    try:
        value = float(text.strip())
    except ValueError:
        return 0.0
    return max(0.0, value)


def _first_problem(entries: list[AppEntry]) -> str | None:
    """저장 전 검사. 문제가 있으면 **첫 번째 것만** 알려준다.

    한 번에 다 쏟아내면 어디부터 고쳐야 할지 알기 어렵다.
    """
    for order, entry in enumerate(entries, start=1):
        if not entry.name.strip():
            return f"{order}번째 항목에 이름이 없습니다."
        if not entry.path.strip():
            return f"'{entry.name}' 의 경로가 비어 있습니다."
        if entry.type not in VALID_APP_TYPES:
            return f"'{entry.name}' 의 종류가 잘못됐습니다: {entry.type}"
    return None
