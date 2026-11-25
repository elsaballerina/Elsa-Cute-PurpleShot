import shutil
import subprocess
from pathlib import Path
from typing import Callable
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from settings import APP_NAME, SettingsWindow, get_save_path


def default_save_path() -> Path:
    return get_save_path()


def copy_bytes_to_clipboard(data: bytes) -> None:
    if shutil.which("wl-copy"):
        proc = subprocess.Popen(
            ["wl-copy", "--type", "image/png"],
            stdin=subprocess.PIPE,
        )
        proc.stdin.write(data)
        proc.stdin.close()
        return

    provider = Gdk.ContentProvider.new_for_bytes("image/png", GLib.Bytes.new(data))
    Gdk.Display.get_default().get_clipboard().set_content(provider)


def copy_file_to_clipboard(image_path: str) -> None:
    copy_bytes_to_clipboard(Path(image_path).read_bytes())


class DestinationPickerWindow(Adw.ApplicationWindow):
    """Post-capture Destination Picker for 🌸 Elsa-Cute-PurpleShot ✨."""

    def __init__(
        self,
        app: Adw.Application,
        image_path: str,
        on_open_editor: Callable[[str], None],
    ) -> None:
        super().__init__(application=app, title=APP_NAME)
        self.image_path = image_path
        self.on_open_editor = on_open_editor
        self.set_default_size(400, -1)
        self.set_resizable(False)

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()

        settings_btn = Gtk.Button.new_from_icon_name("preferences-system-symbolic")
        settings_btn.set_tooltip_text("Settings & Self-Check")
        settings_btn.connect("clicked", lambda *_: SettingsWindow(self).present())
        header.pack_start(settings_btn)

        toolbar_view.add_top_bar(header)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=12,
            margin_bottom=16,
            margin_start=16,
            margin_end=16,
        )

        picture = Gtk.Picture.new_for_filename(image_path)
        picture.set_size_request(-1, 160)
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        frame = Gtk.Frame(child=picture)
        box.append(frame)

        group = Adw.PreferencesGroup()
        actions = [
            ("Open in Image Editor", "document-edit-symbolic", self._open_editor),
            ("Copy to Clipboard", "edit-copy-symbolic", self._copy_clipboard),
            ("Save Directly", "document-save-symbolic", self._save_direct),
            ("Save As…", "document-save-as-symbolic", self._save_as),
        ]
        for label, icon, handler in actions:
            row = Adw.ActionRow(title=label, activatable=True)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            row.connect("activated", handler)
            group.add(row)

        box.append(group)
        toolbar_view.set_content(box)
        self.set_content(toolbar_view)

    def _open_editor(self, _row) -> None:
        self.close()
        self.on_open_editor(self.image_path)

    def _copy_clipboard(self, _row) -> None:
        copy_file_to_clipboard(self.image_path)
        self._notify("Copied to clipboard!")
        self.close()

    def _save_direct(self, _row) -> None:
        dest = default_save_path()
        dest.write_bytes(Path(self.image_path).read_bytes())
        self._notify(f"Saved to {dest.name}")
        self.close()

    def _save_as(self, _row) -> None:
        dialog = Gtk.FileDialog(title="Save Screenshot")
        dialog.set_initial_name(default_save_path().name)
        dialog.save(self, None, self._on_save_as_done)

    def _on_save_as_done(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dialog.save_finish(result)
            if gfile:
                Path(gfile.get_path()).write_bytes(Path(self.image_path).read_bytes())
                self._notify(f"Saved to {gfile.get_basename()}")
                self.close()
        except GLib.Error:
            pass

    def _notify(self, body: str) -> None:
        notif = Gio.Notification.new(APP_NAME)
        notif.set_body(body)
        self.get_application().send_notification("purpleshot-status", notif)
