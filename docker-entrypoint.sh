#!/bin/sh
set -eu

mkdir -p /app/config

if [ ! -f /app/config/settings.json ]; then
  cp /app/defaults/settings.example.json /app/config/settings.json
fi

chown -R app:app /app/config

if [ "${1#-}" != "$1" ]; then
  set -- uvicorn backend.main:app --host 0.0.0.0 "$@"
fi

exec gosu app "$@"
