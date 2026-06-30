#!/usr/bin/env bash
set -euo pipefail

PLIST_LABEL="com.birdmonitor.services"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

echo ""
echo "Eliminando automatizacion de BirdMonitor en macOS..."

if launchctl print "gui/$UID/$PLIST_LABEL" >/dev/null 2>&1; then
  launchctl bootout "gui/$UID" "$PLIST_PATH" >/dev/null 2>&1 || true
fi

if [[ -f "$PLIST_PATH" ]]; then
  rm "$PLIST_PATH"
fi

echo "Deteniendo procesos asociados si siguen activos..."
pkill -f "backend.app.main:app" >/dev/null 2>&1 || true
pkill -f "mediamtx" >/dev/null 2>&1 || true

echo "Automatizacion eliminada."
echo "Nota: no se elimina el proyecto, mediamtx ni los logs."
