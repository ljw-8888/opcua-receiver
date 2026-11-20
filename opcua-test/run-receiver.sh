#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
export PYTHONNOUSERSITE=1 PYTHONPATH=
exec .venv/bin/python receiver_gui.py "$@"
