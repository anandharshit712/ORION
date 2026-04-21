#!/usr/bin/env bash
# Start ORION backend (FastAPI) and frontend (Vite) together.
# Usage: bash start.sh [--no-reload]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/arep_implementation"
FRONTEND_DIR="$SCRIPT_DIR/orion-frontend"

UVICORN_ARGS="arep.api.app:app --host 0.0.0.0 --port 8000 --reload"
if [[ "${1:-}" == "--no-reload" ]]; then
  UVICORN_ARGS="arep.api.app:app --host 0.0.0.0 --port 8000"
fi

# ── colour helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

print_banner() {
  echo -e "${BOLD}${CYAN}"
  echo "  ╔═══════════════════════════════════════╗"
  echo "  ║     ORION  —  AREP  Dev Server        ║"
  echo "  ╚═══════════════════════════════════════╝"
  echo -e "${RESET}"
}

log()  { echo -e "${GREEN}[ORION]${RESET} $*"; }
warn() { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
err()  { echo -e "${RED}[ERROR]${RESET} $*" >&2; }

# ── dependency checks ───────────────────────────────────────────────────────
check_deps() {
  local missing=()
  command -v python  &>/dev/null || command -v python3 &>/dev/null || missing+=("python")
  command -v uvicorn &>/dev/null || missing+=("uvicorn  (pip install arep_implementation/.[api])")
  command -v npm     &>/dev/null || missing+=("npm")
  if [[ ${#missing[@]} -gt 0 ]]; then
    err "Missing dependencies:"
    for m in "${missing[@]}"; do err "  • $m"; done
    exit 1
  fi
}

# ── cleanup on exit ─────────────────────────────────────────────────────────
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  log "Shutting down…"
  [[ -n "$BACKEND_PID"  ]] && kill "$BACKEND_PID"  2>/dev/null && log "Backend stopped  (PID $BACKEND_PID)"
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null && log "Frontend stopped (PID $FRONTEND_PID)"
  exit 0
}
trap cleanup INT TERM

# ── main ────────────────────────────────────────────────────────────────────
print_banner
check_deps

log "Starting backend  →  http://localhost:8000  (docs: /docs)"
(cd "$BACKEND_DIR" && uvicorn $UVICORN_ARGS 2>&1 | sed "s/^/${GREEN}[backend]${RESET} /") &
BACKEND_PID=$!

# give uvicorn a moment to bind the port before vite opens a browser
sleep 1

log "Starting frontend →  http://localhost:5173"
(cd "$FRONTEND_DIR" && npm run dev 2>&1 | sed "s/^/${CYAN}[frontend]${RESET} /") &
FRONTEND_PID=$!

log "Both services running. Press ${BOLD}Ctrl+C${RESET} to stop."
echo -e "  ${BOLD}Backend${RESET}   http://localhost:8000  (API docs: http://localhost:8000/docs)"
echo -e "  ${BOLD}Frontend${RESET}  http://localhost:5173"
echo ""

wait
