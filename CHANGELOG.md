# Changes

## 0.2.1 — experimental

- Add 1 and 2 minute receiving windows alongside 5/10 minutes and indefinite reception.
- Keep the last completed or failed transfer visible when a new receiving session starts.
- Warn when GNOME is still running a cached older extension after installation;
  logging out and back in loads the installed version.

## 0.2.0 — experimental

- Show transfer name/count, received archive bytes, average speed, verification
  and completion/error in the GNOME indicator. Percentages are shown only with
  a known HTTP body length, not estimated from uncompressed file sizes.
- Add completion notifications with Open folder and actionable error messages.
- Export diagnostic JSON from Preferences. It includes only application/system
  versions, known service/transfer states and bounded numerical statistics.
  It never reads logs or exports file/device names, paths, addresses or identity.
- Receive indefinitely or for 5/10 minutes, with a countdown. A running transfer
  retains its activity lock after expiry; new transfers are rejected and Wi-Fi
  is restored through the existing cleanup when the accepted transfer finishes.
- Configure the receiver name and default duration alongside the destination in
  one settings file. Changes apply to the next receiving session.
- Add tests for real TLS uploads across an expired window, graceful draining,
  disconnect cleanup, privacy allowlists and preferences/notification behavior.

No automatic retry, sending UI, transfer history, database or new daemon.
Radio performance/reliability and existing archive limits are unchanged.
New GNOME rendering and physical iPhone transfers still require manual testing.

## 0.1.0 — experimental

Initial GNOME indicator, Intel AX211 receiver integration, Wi-Fi recovery,
Downloads destination, preferences, installer/uninstaller and container CI.
