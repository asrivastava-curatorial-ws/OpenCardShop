#!/usr/bin/env bash
set -euo pipefail
cardshop_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$cardshop_root"
cardshop_python="${OPENCARDSHOP_PYTHON:-python3}"
if ! "$cardshop_python" -c 'import tkinter; from PIL import Image, ImageTk' >/dev/null 2>&1; then
    printf '%s\n' 'OpenCardShop needs Python 3, Tk and Pillow.'
    printf '%s\n' 'Ubuntu / Kubuntu / Mint / Debian: sudo apt install python3 python3-tk python3-pil python3-pil.imagetk'
    printf '%s\n' 'Fedora: sudo dnf install python3 python3-tkinter python3-pillow python3-pillow-tk'
    printf '%s\n' 'Arch: sudo pacman -S python tk python-pillow'
    printf '%s\n' 'After installing dependencies, run: bash run.sh'
    exit 1
fi
exec "$cardshop_python" "$cardshop_root/main.py" "$@"
