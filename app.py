import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from destination import DestinationPickerWindow
from editor import EditorWindow
from portal import RegionCaptureOverlay, ScreenshotPortal
from settings import SettingsWindow, has_critical_issues

CUTE_DARK_PURPLE_CSS = """
window,
.background,
toolbarview {
  background-color: #181324;
  color: #f4eeff;
}

headerbar {
  background-color: #1f1830;
  color: #f4eeff;
}

list,
list.boxed-list,
row,
row.activatable {
  background-color: #251e38;
  color: #f4eeff;
}

row:hover {
  background-color: #342950;
}

label,
image {
  color: #f4eeff;
}

button {
  border-radius: 12px;
}

button.suggested-action {
  background-color: #9b5de5;
  color: #ffffff;
}

.toolbar togglebutton:checked {
  background-color: alpha(#b388ff, 0.28);
  color: #d8bfff;
  border-radius: 12px;
}

frame {
  border-radius: 14px;
  border: 2px solid alpha(#b388ff, 0.50);
}
"""


def apply_purple_theme() -> None:
    style_manager = Adw.StyleManager.get_default()
    style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    provider = Gtk.CssProvider()
    provider.load_from_string(CUTE_DARK_PURPLE_CSS)
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_USER,
        )


class PurpleShotApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="io.github.elsa_cute_purpleshot",
            flags=(
                Gio.ApplicationFlags.HANDLES_COMMAND_LINE
                | Gio.ApplicationFlags.NON_UNIQUE
            ),
        )
        self.add_main_option(
            "capture",
            ord("c"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Trigger an immediate region capture with zoom scope",
            None,
        )
        self.add_main_option(
            "settings",
            ord("s"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Open Settings & System Self-Check",
            None,
        )

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        apply_purple_theme()

    def do_activate(self) -> None:
        pass

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        options = command_line.get_options_dict().end().unpack()
        self.activate()

        # Automatic self-check: if a required tool is missing, show Self-Check first
        if options.get("settings") or has_critical_issues():
            win = SettingsWindow()
            win.set_application(self)
            win.present()
            return 0

        self.start_capture()
        return 0

    def start_capture(self) -> None:
        self.hold()

        def on_region_cropped(crop_path):
            if crop_path:
                picker = DestinationPickerWindow(
                    app=self,
                    image_path=crop_path,
                    on_open_editor=self.open_editor,
                )
                picker.present()
            self.release()

        def on_full_captured(full_path):
            if full_path:
                overlay = RegionCaptureOverlay(
                    app=self,
                    full_image_path=full_path,
                    on_cropped=on_region_cropped,
                )
                overlay.present()
            else:
                self.release()

        ScreenshotPortal.capture(on_full_captured, interactive=False)

    def open_editor(self, image_path: str) -> None:
        editor = EditorWindow(app=self, image_path=image_path)
        editor.present()


def main() -> int:
    app = PurpleShotApp()
    return app.run(sys.argv)
