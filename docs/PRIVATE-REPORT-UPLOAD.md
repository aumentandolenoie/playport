# Private Playport report archive

This is an **opt-in** personal testing feature, not part of the upstream Playport release.

## One-time setup on iPhone

1. Create a **private**, empty GitHub repository for reports, such as `aumentandolenoie/playport-private-reports`. Do **not** use the public Playport source repository.
2. In GitHub create a fine-grained personal access token restricted to that single private repository, with **Contents: Read and write** and no other permissions.
3. In the custom Playport app open a game's options and select **Private log archive**. Enter `owner/repository` and the restricted token.
4. The app verifies that GitHub reports `private: true` and enables upload only after successful verification. The token is stored in the iOS Keychain (this-device-only), not inside the IPA, Git repository or UserDefaults.
5. After configuration, **Report a problem** still opens the ordinary share sheet with the ZIP, while the ZIP is also uploaded to `reports/<game-id>/<original-report-name>.zip` in the private repository. Upload failures display an alert without blocking the share sheet. Each report has an individual time-derived filename.

Reports may contain identifiable paths, account IDs and game metadata. Never publish the archive repository or grant unrestricted token access. Contents API uploads are limited by this feature to 20 MiB, and are not retried automatically if network access fails. GitHub may impose additional limitations. For a failed upload, generate another report after connectivity is restored.

Use **Private log archive → Disable and clear token** to stop automatic uploads and delete credentials locally. This does not delete ZIPs already stored in GitHub.

The app currently uses fine-grained PATs, not a GitHub App OAuth flow. Personal token entry is an intentional setup trade-off for a private development IPA; do not distribute a configured device or token to other users.

## Build status

The Swift implementation is at `app/Sources/S1Probe/UI/PrivateReportUpload.swift`, and the share integration is in `GameDetailView.swift`. A source review is **not** an iOS compile or an on-device test. An IPA needs the complete dependencies, toolchains, SDK, signing and device checks described in `docs/BUILDING.md`. The source-only public GitHub Actions workflow must remain unchanged. A private Codemagic workflow can be designed separately after verifying toolchains and redistribution requirements, but do not publish SDKs, provision files or signed IPAs as public GitHub artifacts.
