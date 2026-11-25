# Hermes integration

Official upstream references:

- Source and installation: https://github.com/NousResearch/hermes-agent
- Documentation: https://hermes-agent.nousresearch.com/docs/
- CLI implementation: https://github.com/NousResearch/hermes-agent/tree/main/hermes_cli

Outbound documentation requests failed DNS resolution in the development sandbox. Consequently, the current upstream installer and command behavior were **not verified against fetched official Hermes documentation in this session**. Coral's installer and bridge are implemented, but the first live deployment must validate the upstream CLI before marking the integration verified.

Coral clones the official repository into `~/.local/share/coral/hermes-agent`, checks out `HERMES_REF` (default `origin/main`), creates a dedicated virtualenv, installs the package, and exposes `~/.local/bin/hermes`. It runs `hermes chat --help` and rejects an installation without the query flag. The installed revision and help text are retained locally. A model provider must be configured with the upstream setup command or Codespaces secrets.

The bridge invokes `~/.local/bin/hermes chat -q PROMPT` in the selected repository. No invented daemon/API protocol is assumed. A subprocess worker records stdout/stderr, its task ID, PID, deadline, and terminal result in a private state directory outside the user-editable repository. Requests arrive only over official Codespaces SSH. Chat Start/Stop enables/disables new invocations and cancels the current one. Conversation context is not automatically resumed between discrete invocations.

The worker deadline covers both the requested duration and the backend's remaining allowance. It terminates the entire task process group at expiration or cancellation. Output is drained through a pipe and capped at 512 KB; exceeding this cap records a failure instead of filling the Codespace's disk. The backend retrieves output over authenticated SSH and persists it independently of Codespace availability. CLI buffering determines whether intermediate progress is immediately visible; final output and errors are always retained when the connection succeeds.

Before first real use, inspect the official documentation and run the CLI help in the selected Codespace. If Hermes's package entry point or query syntax differs, update `codespace/install.sh` and `codespace/runtime.py`, rerun the integration checks, and pin the verified revision. Do not claim live Hermes integration solely from the local development adapter tests.
