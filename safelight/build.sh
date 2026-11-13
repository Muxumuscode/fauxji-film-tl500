#!/usr/bin/env bash
# Builds dist/SajinGenzo (Linux, one file) and a .desktop entry. Run from the safelight folder:   ./build.sh
# Needs Python 3.9+ with venv (Debian/Ubuntu: sudo apt install python3-venv) and the usual Qt runtime libraries
# (Debian/Ubuntu: sudo apt install libxcb-cursor0 libgl1 libegl1).
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
PY=.venv/bin/python
"$PY" -m pip install --quiet -r requirements.txt -r requirements-build.txt
"$PY" -m unittest discover -s tests
"$PY" packaging/make_icon.py build/icon
"$PY" -m PyInstaller --noconfirm --clean --onefile --windowed --name SajinGenzo \
    --icon "$(pwd)/build/icon/safelight.png" --distpath dist --workpath build/pyinstaller --specpath build \
    --exclude-module tkinter --exclude-module unittest --collect-all pillow_heif \
    "$(pwd)/packaging/launcher.py"
cp build/icon/safelight.png dist/safelight.png
cat > dist/sajingenzo.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Sajin Genzō
Comment=Develop your FAUXJI film rolls
Exec=$(pwd)/dist/SajinGenzo %f
Icon=$(pwd)/dist/safelight.png
Categories=Graphics;Photography;
EOF
echo "Built dist/SajinGenzo. To add it to the app menu: cp dist/sajingenzo.desktop ~/.local/share/applications/"
