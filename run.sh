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
echo "🚀 Catbox 图床启动中 http://0.0.0.0:${PORT}"

exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}"
