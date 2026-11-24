#!/usr/bin/env bash
# Barri a Barri — instal·lador per a Linux
#
#   ./instalar.sh               instal·la per a l'usuari actual (sense sudo)
#   sudo ./instalar.sh          instal·la per a tots els usuaris (/opt)
#   ./instalar.sh --desinstalar elimina el joc (el progrés es conserva)
#
set -euo pipefail

APP="barri-a-barri"
NOM="Barri a Barri"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(id -u)" -eq 0 ]; then
    DEST="/opt/$APP"
    BIN_DIR="/usr/local/bin"
    APPS_DIR="/usr/share/applications"
    ICON_DIR="/usr/share/icons/hicolor/256x256/apps"
else
    DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
    DEST="$DATA/$APP-app"
    BIN_DIR="$HOME/.local/bin"
    APPS_DIR="$DATA/applications"
    ICON_DIR="$DATA/icons/hicolor/256x256/apps"
fi

refresh() {
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$APPS_DIR" 2>/dev/null || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$(dirname "$(dirname "$ICON_DIR")")" 2>/dev/null || true
}

if [ "${1:-}" = "--desinstalar" ] || [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$DEST"
    rm -f "$BIN_DIR/$APP" "$APPS_DIR/$APP.desktop" "$ICON_DIR/$APP.png"
    refresh
    echo "✔ $NOM desinstal·lat."
    echo "  (El progrés continua a ~/.local/share/$APP/progress.json)"
    exit 0
fi

if [ ! -x "$SRC/$APP" ] || [ ! -d "$SRC/_internal" ]; then
    echo "✘ Executa aquest script des de la carpeta descomprimida del joc." >&2
    exit 1
fi

if [ "$(uname -m)" != "x86_64" ]; then
    echo "✘ Aquest joc és per a Linux x86_64 (aquest equip és $(uname -m))." >&2
    exit 1
fi

echo "→ Instal·lant $NOM a $DEST"
mkdir -p "$DEST" "$BIN_DIR" "$APPS_DIR" "$ICON_DIR"
rm -rf "$DEST/_internal"
cp -r "$SRC/_internal" "$DEST/"
cp "$SRC/$APP" "$DEST/$APP"
[ -f "$SRC/LLEGEIX-ME.txt" ] && cp "$SRC/LLEGEIX-ME.txt" "$DEST/"
chmod +x "$DEST/$APP"

ln -sf "$DEST/$APP" "$BIN_DIR/$APP"
cp "$SRC/_internal/data/icon.png" "$ICON_DIR/$APP.png"

cat > "$APPS_DIR/$APP.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$NOM
GenericName=Trencaclosques de Barcelona
Comment=Encaixa els 73 barris de Barcelona al mapa
Comment[es]=Encaja los 73 barrios de Barcelona en el mapa
Comment[en]=Fit Barcelona's 73 neighbourhoods into the map
Exec=$DEST/$APP
Icon=$APP
Terminal=false
Categories=Game;LogicGame;Education;Geography;
Keywords=Barcelona;barris;barrios;puzzle;mapa;
StartupWMClass=$APP
EOF
chmod 644 "$APPS_DIR/$APP.desktop"
refresh

echo "✔ Fet! Busca \"$NOM\" al menú d'aplicacions."
case ":$PATH:" in
    *":$BIN_DIR:"*) echo "  També pots escriure: $APP" ;;
    *) echo "  O executa: $DEST/$APP" ;;
esac
