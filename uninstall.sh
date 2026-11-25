#!/usr/bin/env bash
set -e

APP_ID="io.github.elsa_cute_purpleshot"

echo "🧹 Removing 🌸 Elsa-Cute-PurpleShot ✨ launcher and icon..."
rm -f "$HOME/.local/share/applications/$APP_ID.desktop"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg"
rm -rf "$HOME/.config/elsa-cute-purpleshot"

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "✅ Uninstalled cleanly. You can now delete this folder if desired."
