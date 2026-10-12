#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
test -d node_modules || npm ci
export DATABASE_URL="${DATABASE_URL:-sqlite:///./investoffice.db}"
export DEMO_MODE=true
if [[ "${1:-}" == "--lan" ]]; then
  LAN_IP="${LAN_IP:-$(python3 -c 'import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(("192.0.2.1",80)); print(s.getsockname()[0]); s.close()')}"
  export LAN_IP
  python3 -c 'import ipaddress,os; address=ipaddress.ip_address(os.environ["LAN_IP"]); assert address.version == 4 and address.is_private, "LAN_IP must be a private IPv4 address."'
  echo "InvestOffice is available to devices on this Wi-Fi at http://${LAN_IP}:3000"
  echo 'Keep this terminal open. Only share it with people on a trusted private network.'
else
  unset LAN_IP
fi
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT
if [[ "${1:-}" == "--lan" ]]; then
  ./node_modules/.bin/next dev --hostname "$LAN_IP"
else
  npm run dev
fi
