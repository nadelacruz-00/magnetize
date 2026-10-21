#!/usr/bin/env bash
# Install, update or remove Magnetize for the current user.
#
#   curl -fsSL https://raw.githubusercontent.com/nadelacruz-00/magnetize/main/install.sh | bash
#   ./install.sh               # from a clone
#   ./install.sh --uninstall
set -euo pipefail

UUID=magnetize@nadelacruz-00.github.io
REPO=https://github.com/nadelacruz-00/magnetize
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$UUID"
FILES=(metadata.json extension.js prefs.js actions.js presets.js indicator.js stylesheet.css LICENSE)

say() { printf '\033[1m%s\033[0m\n' "$*"; }
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v gnome-shell >/dev/null || die "GNOME Shell isn't installed."
version=$(gnome-shell --version | grep -oE '[0-9]+' | head -1)
(( version >= 47 )) || die "Magnetize needs GNOME 47 or newer (you have $version)."

if [[ ${1:-} == --uninstall ]]; then
    # Disabling first hands back any GNOME shortcuts Magnetize took over.
    gnome-extensions disable "$UUID" 2>/dev/null || true
    rm -rf "$DEST"
    say "Magnetize removed. Log out and back in to finish."
    exit 0
fi

# Use the files next to this script, or fetch them when piped from curl.
src=$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" 2>/dev/null && pwd || true)
if [[ ! -f $src/metadata.json || ! -f $src/presets.js ]]; then
    command -v git >/dev/null || die "git is needed to download Magnetize."
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    git clone --quiet --depth 1 "$REPO" "$tmp/magnetize"
    src=$tmp/magnetize
fi
command -v glib-compile-schemas >/dev/null ||
    die "glib-compile-schemas is missing (on Debian/Ubuntu: sudo apt install libglib2.0-bin)."

rm -rf "$DEST"
mkdir -p "$DEST/schemas" "$DEST/icons"
for f in "${FILES[@]}"; do cp "$src/$f" "$DEST/"; done
cp "$src"/schemas/*.gschema.xml "$DEST/schemas/"
cp "$src"/icons/*.svg "$DEST/icons/"
glib-compile-schemas "$DEST/schemas"
say "Installed to $DEST"

if gnome-extensions info "$UUID" &>/dev/null; then
    gnome-extensions enable "$UUID"
    say "Enabled. If you were updating, log out and back in to load the new version."
else
    # GNOME only finds new extensions at login, so mark it enabled for then.
    enabled=$(gsettings get org.gnome.shell enabled-extensions)
    if [[ $enabled != *"'$UUID'"* ]]; then
        if [[ $enabled == "@as []" || $enabled == "[]" ]]; then
            enabled="['$UUID']"
        else
            enabled="${enabled%]}, '$UUID']"
        fi
        gsettings set org.gnome.shell enabled-extensions "$enabled"
    fi
    say "Log out and back in, and Magnetize will start."
fi

if gnome-extensions info tiling-assistant@ubuntu.com 2>/dev/null | grep -q 'Enabled: Yes'; then
    echo
    echo "Ubuntu's Tiling Assistant is on and will fight with Magnetize's drag snapping."
    echo "Turn it off with:  gnome-extensions disable tiling-assistant@ubuntu.com"
fi
