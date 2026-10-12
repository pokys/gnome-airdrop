# GNOME AirDrop

Experimental AirDrop **receiver** for GNOME, built on OWL and omdrop.
This is an independent project, not affiliated with Apple or GNOME.

Tested on Fedora 44, GNOME Shell 50 and Intel AX211 (iwlwifi).
Other distributions, GNOME versions and Wi-Fi adapters are not verified.
Transfers work, but can be slow and sometimes require retrying.

## Use

Open the AirDrop indicator and enable **Přijímat soubory** (Receive files).
Authenticate with the system password or fingerprint. The receiver appears as
**GNOME-AirDrop** in the iPhone share sheet. Receiving is off after installation
and never starts automatically at boot.

Normal Wi-Fi disconnects while receiving. Turning reception off restores the
previous connection. Keep a backup connection available when testing.
The indicator shows file name/count, received archive bytes, average speed and
verification. Percentages appear only when the HTTP body length is known;
chunked/compressed iPhone payloads usually have no reliable progress percentage.
A completion notification includes **Otevřít složku** (Open folder). Failed
transfers show a short explanation and a suggested next step.
If the iPhone progress circle stops, allow another 40 seconds before stopping.

Files go to the installing user's XDG Downloads folder. Choose another existing folder in **Nastavení…** (Preferences).
Name, folder and duration changes apply on the next receiving session, so saving
settings never interrupts an ongoing transfer.
The service runs separately from GNOME Shell. Disabling the extension does not
stop a transfer; logging out or losing the active login session does.

Choose **Doba příjmu** (Reception duration) before enabling reception: indefinitely,
1, 2, 5 or 10 minutes. The default is saved in the same settings file as the
name and folder. The service starts the countdown after startup. At expiry it
rejects new transfers and lets previously accepted transfers finish, including
the existing upload wait/read timeouts; then it restores Wi-Fi. The GNOME Shell
can restart without losing the timer. A manual stop interrupts immediately.

Preferences also offers **Uložit diagnostiku…** (Save diagnostics). The exported
JSON is built from an allowlist, not filtered logs: application/system versions,
known states/error codes and bounded transfer statistics. It omits names, paths,
addresses, timestamps, IDs, raw errors and runtime identity. It stays local; the
app never sends reports automatically.

## Project layout

- `app/`: receiver, service control, preferences storage and radio orchestration.
- `extension/`: GNOME Shell indicator and graphical preferences.
- `vendor/`: pinned OWL sources (including omdrop radio patches) and Python bindings.
- `packaging/`: installation, removal, systemd and polkit integration.
- `tests/`: isolated protocol, archive, permissions and GNOME indicator checks.
- `tools/`: container build, packaging, validation and publication audit.
- `licenses/`: upstream licenses and source attribution.
- `dist/` and `.build/`: generated, ignored build outputs; never source files.

The repository contains no runtime identity, private keys, transfer logs or
received files. The bundled Apple root certificate is a public trust anchor,
not a user identity.

## Build

Install Podman and Python 3 on the build machine, then run as a regular user:

```sh
./tools/build.sh
```

The build downloads Fedora 44 and development packages into disposable,
isolated rootless Podman storage. It does not install compilers on the host or
change the host's default container storage. The temporary container storage is
removed on exit. The executable and package are generated under `.build/` and
`dist/`. Development sources are bundled, not fetched from mutable branches.

## Install

Runtime requirements: GNOME 50, NetworkManager, Bluetooth/BlueZ, systemd, polkit,
Python 3 with `dbus` and `gi`, libarchive, libev, libpcap, libnl3, `iw`, `ip`,
`nmcli`, `openssl`, `xdg-user-dir`, and GNOME Extensions CLI.
The installer checks requirements and does not install packages, change firewall
rules or enable the service at boot.

```sh
./dist/gnome-airdrop/install.sh
```

When there is more than one Wi-Fi interface, pass the Intel interface name:

```sh
./dist/gnome-airdrop/install.sh YOUR_WIFI_INTERFACE
```

The first installation may require logging out and back in before enabling:

```sh
gnome-extensions enable gnome-airdrop@pokys.github.io
```

If you already use the earlier local ThinkPad AirDrop prototype, switch it off
and use its uninstaller first. Keep your received files. The new installer
refuses to install alongside that prototype. It does not migrate it silently.

## Installed files

The entire receiver is installed under `/opt/gnome-airdrop`, including its
uninstaller. It is independent of the source checkout, which can then be removed.
GNOME and the OS require these small registrations outside that directory:

- `~/.local/share/gnome-shell/extensions/gnome-airdrop@pokys.github.io/`
- `/etc/systemd/system/gnome-airdrop.service`
- `/usr/share/polkit-1/actions/io.github.pokys.gnome-airdrop.policy`

User settings and identity: `~/.local/share/gnome-airdrop/`.
Temporary recovery state: `/run/gnome-airdrop/`.
Private diagnostic logs: `/opt/gnome-airdrop/outputs/` (root access only).
Downloaded files remain in the selected user folder.

```sh
pkexec /opt/gnome-airdrop/bin/control.py stop
sudo /opt/gnome-airdrop/uninstall.sh
```

Removal preserves received files and the source checkout.

## Validation

```sh
./tools/test.sh
./tools/audit.sh
```

Protocol tests use local IPv6 loopback, temporary identities and temporary files;
they do not touch Wi-Fi or start the installed service. A 6 MB transfer, the complete-archive fallback, expired-window TLS uploads,
activity-lock draining, disconnect cleanup and export privacy are covered.
Headless GJS checks cover indicator actions, notification deduplication and
preferences/export behavior. Installer tests use temporary paths and fake OS registrations. Graphical
preferences still need manual
verification in GNOME after installation. No radio operation runs during tests.

## Limitations and recovery

This version reuses the Intel station interface exclusively for AWDL. A refreshed
90-second recovery timer and `ExecStopPost` restore Wi-Fi after normal stop,
process failure or a lost receiver session. Restoration is a best-effort safety
mechanism and does not make experimental wireless code infallible.

If chunked HTTP framing stalls at the boundary after a complete payload, the
receiver accepts it only after validating compression, the archive trailer and
exact file names and sizes from the Ask manifest. Partial data remains rejected.
The original 30-second read timeout is retained; this fallback can delay completion.
It mitigates an observed failure, not the underlying cause of all radio stalls.

Sending from the computer, Apple Contacts-only identity validation and broad
hardware compatibility are outside the current UI. Do not publish private logs
or generated identity files with bug reports.

## Licensing

New integration code is MIT licensed. Bundled components retain their own
licenses: OWL GPL-3.0-or-later, omdrop helper scripts GPL-2.0-only, receiver MIT,
radiotap ISC and libarchive-c CC0. See `LICENSE` and `licenses/SOURCES.txt`.

## Publish from your Git client

Open this project directory, review the staged files, create the initial commit
and push `main` to `https://github.com/pokys/gnome-airdrop.git`. The local remote
is already configured. Do not open the parent experimentation directory as the
repository and do not add `.build/` or `dist/` to Git. Runtime identities and
received files belong outside the repository. Start with this fresh history,
not an old experiment checkout. Run the publication audit after staging changes.

## Automated builds and downloads

GitHub Actions builds and tests the project on pushes to `main`, pull requests
and manual runs. Dependencies and compilation run inside a disposable Fedora 44
container on GitHub's runner. No radio operations run in CI. Build artifacts
are available from the Actions run for 14 days.

Push a version tag such as `v0.2.0` to build, test and publish a GitHub Release:

```sh
git tag v0.2.0
git push origin v0.2.0
```

Successful releases provide:

- `gnome-airdrop-extension-v0.2.0.zip`: GNOME UI only; needs the installed backend.
- `gnome-airdrop-v0.2.0-fedora44-x86_64.tar.gz`: complete receiver/extension bundle
  with installer, uninstaller, documentation and component licenses.
- `SHA256SUMS`: checksums for both downloads.

Download the complete bundle from the repository's **Releases** page, extract it
and run `./gnome-airdrop/install.sh`. Building locally is optional. The installer
still checks host runtime dependencies and does not install them automatically.
The uninstaller is copied to `/opt/gnome-airdrop/uninstall.sh`.

Only the release job receives write permission, after successful tests, and only
for version tags pushed to this repository. Pull requests cannot publish releases.
No personal access token is needed; the workflow uses GitHub's built-in token.
Build results and download artifacts are available on the repository Actions page.

Before tagging a new version, update `app/VERSION` and increment the GNOME integer
`version` in `extension/metadata.json`. Packaging derives the extension's
`version-name` from `app/VERSION`, and release CI rejects mismatching tags.

For an existing installation, switch reception off and uninstall the previous
bundle before installing this version. The current installer refuses to overwrite
an existing installation; received files survive removal, settings/identity do not.
