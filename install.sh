#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID="io.github.elsa_cute_purpleshot"

echo "🌸 Installing dependencies for 🌸 Elsa-Cute-PurpleShot ✨ (v1.0)..."
sudo dnf install -y \
    python3-gobject \
    gtk4 \
    libadwaita \
    python3-cairo \
    python3-pillow \
    wl-clipboard

echo "🎨 Installing cute purple icon..."
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$ICON_DIR"
cp "$SCRIPT_DIR/icon.svg" "$ICON_DIR/$APP_ID.svg"

echo "🚀 Creating GNOME application launcher..."
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

cat << DESKTOP > "$DESKTOP_DIR/$APP_ID.desktop"
[Desktop Entry]
Name=🌸 Elsa-Cute-PurpleShot ✨
Comment=Cute Fedora-native screenshot & annotation tool
Exec=python3 "$SCRIPT_DIR" --settings
Icon=$APP_ID
Terminal=false
Type=Application
Categories=Graphics;Utility;
Keywords=screenshot;capture;greenshot;purpleshot;elsa;
Actions=Capture;

[Desktop Action Capture]
Name=Capture Region
Exec=python3 "$SCRIPT_DIR" --capture
DESKTOP

chmod +x "$DESKTOP_DIR/$APP_ID.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo ""
echo "✅ Done! 🌸 Elsa-Cute-PurpleShot ✨ v1.0 is installed."
echo "💡 Bind 'python3 \"$SCRIPT_DIR\" --capture' to Shift+Super+S or Print in Settings → Keyboard."
