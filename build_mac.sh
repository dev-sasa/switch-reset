#!/bin/bash
# Baut ./dist/switch_reset (eigenstaendige macOS-Programmdatei, kein Python noetig zum Ausfuehren)
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip pyserial pyinstaller
pyinstaller --onefile --console --name switch_reset switch_reset.py
echo
echo "Fertig: dist/switch_reset"
