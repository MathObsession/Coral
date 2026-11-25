#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/backend"
export CORAL_DEMO=1
export CORAL_DATABASE="$PWD/.coral/coral.sqlite"
if [ ! -f .coral/local-key ]; then
  mkdir -p .coral
  python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' > .coral/local-key
  chmod 600 .coral/local-key
fi
export CORAL_ENCRYPTION_KEY="$(cat .coral/local-key)"
echo 'Coral local backend: http://127.0.0.1:8000'
echo 'Serve the dashboard separately: python3 -m http.server 8080 --directory website'
exec python3 -m uvicorn coral.app:production_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
