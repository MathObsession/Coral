#!/usr/bin/env bash
set -euo pipefail
umask 077

# Hermes Agent v0.23.4. Use the upstream installer to provision its managed Python.
hermes_commit=8fc0374447313e276f6b9a2764bfc750190c966a
coral_dir="$HOME/.local/share/coral"
launcher="$HOME/.local/bin/hermes"
mkdir -p "$coral_dir"
exec 9>"$coral_dir/hermes-install.lock"
flock -w 180 9

if [ -x "$launcher" ] && [ -f "$coral_dir/hermes-version" ] &&
    [ "$(cat "$coral_dir/hermes-version")" = "$hermes_commit" ]; then
  exit 0
fi

curl --fail --silent --show-error --location --retry 3 \
  "https://raw.githubusercontent.com/NousResearch/hermes-agent/$hermes_commit/scripts/install.sh" \
  -o "$coral_dir/hermes-upstream-install.sh"
bash "$coral_dir/hermes-upstream-install.sh" --commit "$hermes_commit" \
  --dir "$coral_dir/hermes-agent" --non-interactive --skip-browser --skip-computer-use

"$launcher" chat --help > "$coral_dir/hermes-cli-help.txt"
grep -q -- '--oneshot' "$coral_dir/hermes-cli-help.txt"
grep -q -- '--query' "$coral_dir/hermes-cli-help.txt"
printf '%s\n' "$hermes_commit" > "$coral_dir/hermes-version"
