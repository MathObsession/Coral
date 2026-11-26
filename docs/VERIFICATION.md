# Verification record

This document distinguishes implemented source, executed local checks, and live checks that still require configuration. It does not claim a GitHub/Hermes deployment from offline tests.

Final result: **41 automated checks passed** — 31 backend/runtime, six web, and four native. Both native applications were launched through Xcode. Development bundles are in `build/deliverables/`; real iPhone screenshots and accessibility dumps are in `build/screenshots/`.

Render Free adaptation: **37 backend/runtime tests and six web tests pass**. The six additional backend checks cover required persistent-storage configuration, PostgreSQL SQL/precision handling, TLS and bound values, safe reconnection, and authenticated external scheduling without resetting inactivity. One live PostgreSQL integration test is skipped until a dedicated `CORAL_TEST_DATABASE_URL` is supplied. Native source/API contracts did not change in this adaptation.

## Executed

- Inspected every original asset: mascot PNG, all three screen PNGs, their HTML sources, and `assets/tactile_playful_craft/DESIGN.md`.
- Built the shared SwiftUI project with Xcode 27.2 for macOS and the iOS Simulator SDK. Both builds succeeded.
- Through Xcode MCP, launched `Coral-macOS` on **My Mac** (macOS 27.3). The tool reported a successful launch with no build errors.
- Through Xcode MCP, selected **Coral-iOS → iPhone 17**, built and launched it successfully with no build errors. An initial iPhone 18 Pro device-interaction attempt timed out; the subsequent ordinary Xcode launch on iPhone 17 succeeded.
- Ran the four native XCTest cases through Xcode MCP: usage decoding, task/schedule relationship decoding, nonnegative counter formatting, and SSH command injection rejection. All four passed.
- Ran 31 backend/runtime tests covering real local file/shell round trips, authorization, encrypted token storage, replay-resistant authentication exchange, duplicate starts, task idempotency, inactivity, extensions and GitHub idle settings, quota rejection, honest accounting during shutdown failure, UTC midnight accounting, schedule wake/result/shutdown, duration failure, missed recurrences, shutdown retries, crash recovery, request size limits, and actual remote-worker subprocess streaming/cancellation/deadlines/output limits.
- Ran six web contract/security checks for signed-out navigation, escaped output, read-only background refresh, throttled activity, secure URLs, and all screen renderers. All six passed. JavaScript syntax and shell scripts were also checked.
- Captured the running iPhone 17 app's real screenshot and accessibility hierarchy through Xcode's device tools. The sign-in page renders the preserved fox and complete onboarding controls within the phone's safe area.
- Interacted with the iPhone app: opened the backend settings sheet, inspected the URL and account controls, attempted sign-in with the unavailable localhost backend, confirmed a clear connection error, and dismissed it while the app remained running. UI review caught and corrected text shadows and deferred the alert-binding update to avoid publishing during view updates. Temporary device-interaction sessions were closed when finished.
- Verified installed official GitHub CLI help for `gh codespace ssh`, `create`, `list`, `stop`, and `gh api`. The official SSH/config flags, SSH-server devcontainer feature, environment-token API invocation, and Codespace lifecycle commands are used.

## Environment limits encountered

- Shell-based CoreSimulator requests, display capture, and localhost server binds were denied in the managed shell sandbox. Xcode MCP provided successful native app launches and native tests independently of those shell failures.
- Xcode's `DocumentationSearch` failed twice with `Failed to create the text encoder`. Available run destinations were inspected directly through Xcode's tools. Native Mac apps run on My Mac; iPhone runs use Xcode's iOS simulator destination.
- Outbound requests to official GitHub and Hermes documentation failed DNS resolution. The Hermes installer's upstream CLI contract remains pending live verification. The installer checks CLI help at installation and fails if the supported entry point changes.
- `gh auth status` reported an invalid existing login. No Codespace was created, no repository was published, and no live OAuth token was available.
- The starting folder was not a Git repository, and its managed `.git` path rejected `git init`. Source and deployment workflows were written in the authorized workspace; initial commit/push remains a local setup step.

## Reproduce

```bash
python3 -m pytest backend/tests -q
node --test website/tests/*.test.cjs
bash -n codespace/install.sh scripts/*.sh
```

In Xcode, select **Coral-macOS → My Mac** and run tests, then **Coral-iOS → an available iPhone simulator** and Run. Alternatively use `scripts/test.sh` and `scripts/test-simulator.sh` on an unrestricted local development host. Shell builds in a nested managed sandbox may require `OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox'` to let Swift's own macro plugin subprocess run; this is unnecessary for ordinary Xcode MCP builds.

Complete [LIVE_ACCEPTANCE.md](LIVE_ACCEPTANCE.md) with your configured backend, GitHub account, and real Hermes provider before treating the cloud path as live-verified.
