#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_ACTIVATE="$ROOT_DIR/.venv/bin/activate"
SERVER_PID=""
ROBOT_PID=""

cleanup() {
  trap - INT TERM EXIT

  if [[ -n "$ROBOT_PID" ]] && kill -0 "$ROBOT_PID" 2>/dev/null; then
    kill "$ROBOT_PID" 2>/dev/null || true
  fi
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
}

trap cleanup INT TERM EXIT

if [[ ! -f "$VENV_ACTIVATE" ]]; then
  echo "[ERROR] Python virtual env not found: $VENV_ACTIVATE"
  echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r brain/requirements.txt"
  exit 1
fi

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "[ERROR] .env not found"
  echo "Run: cp .env.example .env && edit DASHSCOPE_API_KEY"
  exit 1
fi

if ! grep -Eq '^DASHSCOPE_API_KEY=.+' "$ROOT_DIR/.env"; then
  echo "[ERROR] DASHSCOPE_API_KEY is missing in .env"
  exit 1
fi

source "$VENV_ACTIVATE"

# 若 8090 端口已被占用则先杀掉，避免 "address already in use"
if lsof -ti:8090 >/dev/null 2>&1; then
  echo "[INFO] Port 8090 in use, releasing..."
  lsof -ti:8090 | xargs kill -9 2>/dev/null || true
  sleep 1
fi

if [[ ! -x "$ROOT_DIR/cerebellum/build/robot_brain" ]]; then
  echo "[INFO] robot_brain not found, building..."
  cmake -S "$ROOT_DIR/cerebellum" -B "$ROOT_DIR/cerebellum/build"
  cmake --build "$ROOT_DIR/cerebellum/build" --target robot_brain -j
fi

echo "[INFO] Starting backend: python server.py"
python "$ROOT_DIR/server.py" &
SERVER_PID=$!

sleep 1
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
  echo "[ERROR] Backend failed to start"
  exit 1
fi

echo "[INFO] Starting robot brain: ./cerebellum/build/robot_brain"
"$ROOT_DIR/cerebellum/build/robot_brain" &
ROBOT_PID=$!

echo "[OK] All services are up"
echo "[INFO] Open: http://127.0.0.1:8090"
if command -v open &>/dev/null; then
  open "http://127.0.0.1:8090" >/dev/null 2>&1 || true
fi
echo "[INFO] Press Ctrl+C to stop both services"

while true; do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "[WARN] Backend stopped"
    break
  fi
  if ! kill -0 "$ROBOT_PID" 2>/dev/null; then
    echo "[WARN] robot_brain stopped"
    break
  fi
  sleep 1
done
