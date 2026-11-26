# Hermes integration

Official upstream references:

- Source and installation: https://github.com/NousResearch/hermes-agent
- Documentation: https://hermes-agent.nousresearch.com/docs/
- CLI implementation: https://github.com/NousResearch/hermes-agent/tree/main/hermes_cli

On the first Codespace start, Coral runs Hermes Agent v0.23.4's pinned upstream CLI installer over GitHub Codespaces SSH. The upstream installer prepares managed Python 3.14 and installs Hermes to `~/.local/bin/hermes`. Coral verifies the `--oneshot` and `--query` flags and records the release commit. Installer output is available at `~/.local/share/coral/hermes-install.log` inside the Codespace. [Official installation guide](https://hermes-agent.nousresearch.com/docs/getting-started/installation)

Start the Codespace and open **Hermes → Model** on Mac or iPhone. Coral loads the provider catalog from Hermes running in that Codespace. Select a provider and model, or choose **Add OpenAI-compatible endpoint** and enter a name, base URL, model ID, and optional API key. An endpoint on `localhost` refers to the Codespace. The API key goes to Hermes's private configuration in the Codespace.

For providers that need browser authentication or additional configuration, open the interactive wizard from the Mac app or run `~/.local/bin/hermes model` over `gh codespace ssh`. For the Mac's separate SSH connection, grant the local GitHub CLI access with `gh auth refresh -h github.com -s codespace` if needed. [Hermes providers](https://hermes-agent.nousresearch.com/docs/integrations/providers)

### GitHub Copilot

Open **Hermes → Model → Set up GitHub Copilot** and authorize the GitHub account that has Copilot access during device sign-in. This uses the optional Hermes Labs provider. Which models and limits apply depend on that GitHub account's Copilot plan and policy. The same setup works through a Codespace terminal.

```bash
hermes plugins install github-copilot --enable
hermes auth add copilot
hermes model
```

Select **GitHub Copilot** and a model in Hermes. The provider credentials stay in the Codespace. [Hermes GitHub Copilot plugin](https://github.com/NousResearch/hermes-labs-plugins/tree/main/github-copilot)

### Coral tools

Ask Hermes to schedule a follow-up task, list upcoming work, pause or resume a schedule, check remaining time, or inspect recent task statuses. The `coral-workspace` plugin uses a credential scoped to the running Hermes task and its workspace. The Coral scheduler stores and runs the schedule independently of the app and Codespace. Use a start time with a time zone when scheduling from chat.

The bridge invokes `~/.local/bin/hermes chat --oneshot --query PROMPT` in the selected repository. A subprocess worker records stdout and stderr, the task ID, PID, deadline, and terminal result in a private state directory. Start Hermes enables new invocations. Stop Hermes cancels the current invocation and disables new ones. Each task opens a separate conversation. [Hermes CLI commands](https://hermes-agent.nousresearch.com/docs/reference/cli-commands)

The worker deadline covers both the requested duration and the backend's remaining allowance. It terminates the entire task process group at expiration or cancellation. Output is drained through a pipe and capped at 512 KB; exceeding this cap records a failure instead of filling the Codespace's disk. The backend retrieves output over authenticated SSH and persists it independently of Codespace availability. CLI buffering determines whether intermediate progress is immediately visible; final output and errors are always retained when the connection succeeds.
