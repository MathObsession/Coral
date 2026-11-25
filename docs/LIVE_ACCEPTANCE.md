# First live-session acceptance

These checks require the user's configured GitHub OAuth app, backend, Codespaces billing, and Hermes model provider. They are separate from automated local checks.

1. Inspect the official Hermes documentation and validate `hermes chat -q` against the installed CLI help. Pin the reviewed `HERMES_REF`.
2. Authenticate the Mac app with GitHub. Confirm the callback returns a one-use code, and profiles expose no GitHub token/private key.
3. In Profiles, select the repository and create or bind the account's Codespace. Confirm the repository and billable account in GitHub. Observe starting → available.
4. Configure the model provider through `gh codespace ssh --codespace NAME` and `hermes setup`. Submit a real Hermes task, inspect progress/final output, and cancel another task.
5. Create and edit a UTF-8 workspace file, save it, and read it with the terminal command interface. Confirm traversal and protected file requests fail.
6. Connect the embedded Mac SSH console and open the same profile in Terminal/iTerm. Confirm its GitHub CLI identity is the profile's account. Close the console without stopping the backend session.
7. Open the iPhone app in Xcode's selected iPhone runtime. Authenticate and observe the same state and task history. Test Home, Hermes, Schedules, and More → Files/Terminal/Usage/Extended/Profiles/Settings.
8. Poll continuously with the app open but perform no meaningful action for ten minutes. Confirm the backend records inactivity and GitHub confirms Shutdown. Repeat with the app closed.
9. Enable a 15-minute extension and leave the app. Verify the extension expires and the environment shuts down without bypassing allowance.
10. Schedule a one-time task a few minutes ahead while the Codespace is stopped. Close both apps. Verify start, real Hermes result, persisted inbox entry, usage consumption, and immediate shutdown after completion.
11. Edit/pause/resume/delete recurring tasks. Verify occurrence history and that one occurrence is never dispatched twice.
12. Configure a short task-duration limit and deliberately exceed it. Confirm task failure, process-group termination, and shutdown after a scheduled task.
13. Near allowance exhaustion, verify new starts/tasks are rejected and extended mode cannot run past the session deadline. Review real GitHub compute usage alongside Coral accounting.
14. Restart the backend during a task. Confirm it records interruption without replay and stops the Codespace. If installed, stop the main service and verify the independent watchdog timer.
15. Link a second GitHub account, select its own Codespace, and verify billing and SSH account selection. Confirm only one account-level Coral session runs at once.
