#!/usr/bin/env bash
set -euo pipefail
PACKAGE=$(cd -- "$(dirname -- "$0")" && pwd)
if [[ $EUID != 0 ]]; then exec sudo /bin/bash "$PACKAGE/uninstall.sh"; fi
TARGET=/opt/gnome-airdrop
[[ -f $TARGET/INSTALLATION-MARKER ]] || { echo 'Tato instalace neexistuje.'; exit 2; }
readarray -t OWNER_INFO < <(python3 - "$TARGET/config.json" <<'PY'
import json, pwd, sys
c=json.load(open(sys.argv[1]))
u=pwd.getpwuid(c['owner_uid'])
assert u.pw_uid != 0 and u.pw_name == c['owner_name']
assert c['user_data'] == u.pw_dir + '/.local/share/gnome-airdrop'
print(u.pw_name); print(u.pw_uid); print(u.pw_dir); print(c['user_data'])
PY
)
[[ ${#OWNER_INFO[@]} == 4 ]]
OWNER=${OWNER_INFO[0]} OWNER_UID=${OWNER_INFO[1]} OWNER_HOME=${OWNER_INFO[2]} DATA=${OWNER_INFO[3]}
systemctl stop gnome-airdrop.service
python3 "$TARGET/bin/service.py" recover
runuser -u "$OWNER" -- env XDG_RUNTIME_DIR="/run/user/$OWNER_UID" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$OWNER_UID/bus" \
  gnome-extensions disable gnome-airdrop@pokys.github.io || true
runuser -u "$OWNER" -- rm -rf -- \
  "$OWNER_HOME/.local/share/gnome-shell/extensions/gnome-airdrop@pokys.github.io" "$DATA"
rm -f /etc/systemd/system/gnome-airdrop.service \
  /usr/share/polkit-1/actions/io.github.pokys.gnome-airdrop.policy
rm -rf -- "$TARGET"
systemctl daemon-reload
echo 'Rozsireni a backend odstraneny. Prijate soubory zustaly zachovane.'
