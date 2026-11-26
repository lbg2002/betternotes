#!/bin/bash
# Development runner — runs BetterNotes without installing
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Compile GSettings schema locally
mkdir -p "$SCRIPT_DIR/build/schemas"
glib-compile-schemas "$SCRIPT_DIR/data/" --targetdir="$SCRIPT_DIR/build/schemas" 2>/dev/null || true

export GSETTINGS_SCHEMA_DIR="$SCRIPT_DIR/build/schemas"
export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"

exec python3 -c "
import os, sys, signal, gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
signal.signal(signal.SIGINT, signal.SIG_DFL)
sys.path.insert(0, '$SCRIPT_DIR/src')
os.environ['BETTERNOTES_DEV'] = '1'
from betternotes.application import BetterNotesApp
sys.exit(BetterNotesApp(version='dev').run(sys.argv))
" "$@"
