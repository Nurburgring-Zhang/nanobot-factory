#!/usr/bin/env bash
# IMDF Linux/macOS Launcher — Double-click or `./start.sh`
set -e
cd "$(dirname "$0")"
python3 run.py "$@"
