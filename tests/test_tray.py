"""트레이 아이콘 테스트.

트레이 아이콘이 실제로 뜨는지는 자동으로 확인할 수 없다(화면에 그려지는 것이라).
대신 **틀리면 크게 곤란해지는 두 가지**를 검증한다.

  ⭐ 트레이 스레드가 화면을 직접 건드리지 않는가 (여기가 틀리면 프로그램이 이유 없이 죽는다)
  ⭐ 트레이를 못 쓰는 환경에서 창을 숨겨버리지 않는가 (프로그램이 통째로 사라진다)
"""

from clap_launcher.ui import tray


class TestLabels:
    def test_메뉴_글자는_누르면_일어날_일을_말한다(self):
        """'듣는 중'이라고 적으면 그게 상태인지 동작인지 알 수 없다."""
        assert tray.toggle_label(listening=True) == "듣기 중지"
        assert tray.toggle_label(listening=False) == "듣기 시작"

    def test_설명에_마이크_사용_여부가_드러난다(self):
        """⭐ 마이크를 언제 잡는지는 프라이버시 문제라 항상 보여야 한다."""
        assert "듣는 중" in tray.status_text(True)
        assert "마이크 사용 안 함" in tray.status_text(False)

    def test_듣는_중일_때만_색이_다르다(self):
        assert tray.status_color(True) != tray.status_color(False)


class TestIconImage:
    def test_아이콘_이미지를_만든다(self):
        image = tray.make_icon_image(listening=True)
        assert image is not None, "Pillow 가 있으면 이미지가 나와야 한다"
        assert image.size == (tray.ICON_SIZE, tray.ICON_SIZE)
        assert image.mode == "RGBA"      # 배경이 투명해야 어떤 테마에서도 자연스럽다

    def test_상태에_따라_다른_이미지가_나온다(self):
        listening = tray.make_icon_image(True).tobytes()
        idle = tray.make_icon_image(False).tobytes()
        assert listening != idle, "색이 같으면 아이콘만 보고 상태를 알 수 없다"


class TestThreadHandover:
    """⭐ 이 파일에서 가장 중요한 부분.

    pystray 메뉴 콜백은 트레이 스레드에서 불린다. 거기서 Tkinter 위젯을 건드리면
    프로그램이 이유 없이 멈추거나 죽는다. 그래서 '큐에 넣고, 화면 스레드가 꺼내 실행'한다.
    """

    def _icon(self):
        self.log = []
        return tray.TrayIcon(
            on_show=lambda: self.log.append("show"),
            on_toggle_listening=lambda: self.log.append("toggle"),
            on_quit=lambda: self.log.append("quit"),
        )

    def test_넘긴_일은_바로_실행되지_않는다(self):
        """트레이 스레드에서는 **아무것도 하지 않아야** 한다. 큐에 넣기만 한다."""
        icon = self._icon()
        icon._hand_over(icon._on_show)
        assert self.log == []

    def test_화면_스레드가_꺼내야_실행된다(self):
        icon = self._icon()
        icon._hand_over(icon._on_show)

        assert icon.process_pending() == 1
        assert self.log == ["show"]

    def test_밀린_것을_순서대로_전부_처리한다(self):
        icon = self._icon()
        for action in (icon._on_show, icon._on_toggle, icon._on_quit):
            icon._hand_over(action)

        assert icon.process_pending() == 3
        assert self.log == ["show", "toggle", "quit"]

    def test_할_일이_없으면_아무_일도_없다(self):
        icon = self._icon()
        assert icon.process_pending() == 0

    def test_하나가_실패해도_나머지는_처리된다(self):
        """메뉴 하나가 터졌다고 종료가 안 되면 프로그램을 끌 방법이 없어진다."""
        icon = self._icon()

        def 폭발():
            raise RuntimeError("일부러 터뜨림")

        icon._hand_over(폭발)
        icon._hand_over(icon._on_quit)

        assert icon.process_pending() == 2
        assert self.log == ["quit"]


class TestLifecycle:
    def _icon(self):
        return tray.TrayIcon(on_show=lambda: None, on_toggle_listening=lambda: None,
                             on_quit=lambda: None)

    def test_띄우기_전에는_running_이_아니다(self):
        """⭐ available(라이브러리가 있다)과 running(실제로 떠 있다)은 다르다.

        이걸 헷갈리면, 트레이를 못 띄운 환경에서 창을 숨겨 프로그램이 통째로 사라진다.
        """
        assert self._icon().running is False

    def test_띄우지_않고_멈춰도_안전하다(self):
        self._icon().stop()      # 예외가 나면 종료 경로가 막힌다

    def test_여러_번_멈춰도_안전하다(self):
        icon = self._icon()
        icon.stop()
        icon.stop()

    def test_아이콘이_없을_때_상태_변경은_조용히_넘어간다(self):
        icon = self._icon()
        icon.set_listening(True)      # 예외 없이 지나가야 한다
        assert icon._listening is True

    def test_아이콘이_없을_때_알림도_조용히_넘어간다(self):
        self._icon().notify("아무 일도 일어나지 않아야 한다")
