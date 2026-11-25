import datetime
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple
from gi.repository import Adw, Gdk, GLib, Gtk

APP_NAME = "🌸 Elsa-Cute-PurpleShot v1.0 ✨"
CONFIG_DIR = Path.home() / ".config" / "elsa-cute-purpleshot"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "save_dir": str(
        Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES))
        / "Screenshots"
    ),
    "filename_prefix": "Elsa-Cute_",
    "default_color": "#9b5de5",
    "default_line_width": 3,
}


def load_config() -> Dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except Exception:
            pass
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def get_save_path() -> Path:
    cfg = load_config()
    target_dir = Path(cfg["save_dir"]).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    prefix = cfg.get("filename_prefix", "Elsa-Cute_")
    return target_dir / f"{prefix}{stamp}.png"


def run_self_check() -> List[Tuple[str, bool, str]]:
    """Checks all required tools and optional extensions."""
    results: List[Tuple[str, bool, str]] = []

    # 1. Wayland Clipboard (wl-copy)
    if shutil.which("wl-copy"):
        results.append(("Wayland Clipboard (wl-copy)", True, "Installed and ready"))
    else:
        results.append((
            "Wayland Clipboard (wl-copy)",
            False,
            "Missing — run: sudo dnf install wl-clipboard",
        ))

    # 2. Pillow (Image Processing)
    if importlib.util.find_spec("PIL"):
        results.append(("Pillow (python3-pillow)", True, "Installed and ready"))
    else:
        results.append((
            "Pillow (python3-pillow)",
            False,
            "Missing — run: sudo dnf install python3-pillow",
        ))

    # 3. PyCairo (Drawing Engine)
    if importlib.util.find_spec("cairo"):
        results.append(("PyCairo (python3-cairo)", True, "Installed and ready"))
    else:
        results.append((
            "PyCairo (python3-cairo)",
            False,
            "Missing — run: sudo dnf install python3-cairo",
        ))

    # 4. Optional GNOME No-Flash Extension
    try:
        out = subprocess.check_output(
            ["gnome-extensions", "info", "no-screenshot-flash@elsa"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        if "ACTIVE" in out or "ENABLED" in out:
            results.append(("No-Flash Extension (Optional)", True, "Active"))
        else:
            results.append((
                "No-Flash Extension (Optional)",
                False,
                "Installed but not enabled",
            ))
    except Exception:
        results.append((
            "No-Flash Extension (Optional)",
            True,
            "Not installed (using default GNOME flash)",
        ))

    return results


def has_critical_issues() -> bool:
    """Returns True if a required dependency (first 3 checks) is missing."""
    checks = run_self_check()[:3]
    return any(not ok for _, ok, _ in checks)


class SettingsWindow(Adw.PreferencesWindow):
    """Cute Preferences & System Self-Check window for 🌸 Elsa-Cute-PurpleShot ✨."""

    def __init__(self, parent: Gtk.Window | None = None) -> None:
        super().__init__(title=f"{APP_NAME} — Settings")
        if parent:
            self.set_transient_for(parent)
        self.set_default_size(520, 480)
        self.cfg = load_config()

        self._build_general_page()
        self._build_self_check_page()

    def _build_general_page(self) -> None:
        page = Adw.PreferencesPage(
            title="General",
            icon_name="preferences-system-symbolic",
        )

        # Saving options
        save_group = Adw.PreferencesGroup(title="Saving & Files")

        dir_row = Adw.EntryRow(title="Save Folder")
        dir_row.set_text(self.cfg["save_dir"])
        dir_row.connect("changed", self._on_save_dir_changed)
        save_group.add(dir_row)

        prefix_row = Adw.EntryRow(title="Filename Prefix")
        prefix_row.set_text(self.cfg["filename_prefix"])
        prefix_row.connect("changed", self._on_prefix_changed)
        save_group.add(prefix_row)

        page.add(save_group)

        # Editor defaults
        editor_group = Adw.PreferencesGroup(title="Editor Defaults")

        color_row = Adw.ActionRow(title="Default Annotation Color")
        rgba = Gdk.RGBA()
        rgba.parse(self.cfg["default_color"])
        color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        color_btn.set_rgba(rgba)
        color_btn.set_valign(Gtk.Align.CENTER)
        color_btn.connect("notify::rgba", self._on_color_changed)
        color_row.add_suffix(color_btn)
        editor_group.add(color_row)

        width_row = Adw.SpinRow.new_with_range(1, 20, 1)
        width_row.set_title("Default Stroke Width")
        width_row.set_value(self.cfg["default_line_width"])
        width_row.connect("notify::value", self._on_width_changed)
        editor_group.add(width_row)

        page.add(editor_group)
        self.add(page)

    def _build_self_check_page(self) -> None:
        page = Adw.PreferencesPage(
            title="Self-Check",
            icon_name="emblem-ok-symbolic",
        )

        group = Adw.PreferencesGroup(
            title="System Health & Dependencies",
            description="Verifies that all required tools are installed for smooth operation.",
        )

        for name, ok, detail in run_self_check():
            row = Adw.ActionRow(title=name, subtitle=detail)
            icon_name = "emblem-ok-symbolic" if ok else "dialog-warning-symbolic"
            icon = Gtk.Image.new_from_icon_name(icon_name)
            row.add_prefix(icon)
            group.add(row)

        page.add(group)
        self.add(page)

    def _on_save_dir_changed(self, row: Adw.EntryRow) -> None:
        self.cfg["save_dir"] = row.get_text().strip() or DEFAULT_CONFIG["save_dir"]
        save_config(self.cfg)

    def _on_prefix_changed(self, row: Adw.EntryRow) -> None:
        self.cfg["filename_prefix"] = row.get_text()
        save_config(self.cfg)

    def _on_color_changed(self, btn: Gtk.ColorDialogButton, _pspec) -> None:
        c = btn.get_rgba()
        hex_color = f"#{int(c.red * 255):02x}{int(c.green * 255):02x}{int(c.blue * 255):02x}"
        self.cfg["default_color"] = hex_color
        save_config(self.cfg)

    def _on_width_changed(self, row: Adw.SpinRow, _pspec) -> None:
        self.cfg["default_line_width"] = int(row.get_value())
        save_config(self.cfg)
