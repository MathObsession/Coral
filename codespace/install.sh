#!/usr/bin/env bash
set -euo pipefail
# Official source: https://github.com/NousResearch/hermes-agent
# Set HERMES_REF to a reviewed tag or commit for reproducible production installs.
coral_hermes_dir="$HOME/.local/share/coral/hermes-agent"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/coral"
if [ ! -d "$coral_hermes_dir/.git" ]; then
  git clone https://github.com/NousResearch/hermes-agent.git "$coral_hermes_dir"
fi
git -C "$coral_hermes_dir" fetch --tags origin
git -C "$coral_hermes_dir" checkout --detach "${HERMES_REF:-origin/main}"
python3 -m venv "$coral_hermes_dir/.venv"
"$coral_hermes_dir/.venv/bin/python" -m pip install --upgrade pip
"$coral_hermes_dir/.venv/bin/python" -m pip install -e "$coral_hermes_dir"
ln -sf "$coral_hermes_dir/.venv/bin/hermes" "$HOME/.local/bin/hermes"
# Fail explicitly if upstream changes the supported noninteractive entry point.
"$HOME/.local/bin/hermes" chat --help > "$coral_hermes_dir/coral-cli-help.txt"
if ! "$coral_hermes_dir/.venv/bin/python" -c 'import pathlib,sys; text=pathlib.Path(sys.argv[1]).read_text(); sys.exit(0 if "-q" in text or "--query" in text else 1)' "$coral_hermes_dir/coral-cli-help.txt"; then
  echo 'Hermes CLI has changed. Review official docs and update Coral runtime before continuing.' >&2
  exit 1
fi
git -C "$coral_hermes_dir" rev-parse HEAD > "$coral_hermes_dir/coral-version.txt"
echo 'Hermes installed. Run ~/.local/bin/hermes setup through gh codespace ssh to configure your model provider.'
