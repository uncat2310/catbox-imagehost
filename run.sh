#!/bin/bash
# Catbox 图床 —— 启动脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 激活虚拟环境
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
else
    echo "❌ 请先安装依赖: python3.11 -m venv venv && source venv/bin/activate && pip install -r backend/requirements.txt"
    exit 1
fi

PORT="${PORT:-7800}"
export HOST="${HOST:-127.0.0.1}"
echo "🚀 个人 Catbox 图床启动中 http://${HOST}:${PORT}"

exec uvicorn backend.main:app --host "${HOST}" --port "${PORT}" --workers 1 --env-file .env
