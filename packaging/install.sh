#!/usr/bin/env bash
set -euo pipefail
PACKAGE=$(cd -- "$(dirname -- "$0")" && pwd)
if [[ $EUID != 0 ]]; then exec sudo /bin/bash "$PACKAGE/install.sh" "$@"; fi
[[ -n ${SUDO_USER:-} && ${SUDO_UID:-0} != 0 ]] || { echo 'Spustit z bezneho uzivatelskeho uctu.'; exit 2; }
TARGET=/opt/gnome-airdrop
UNIT=/etc/systemd/system/gnome-airdrop.service
POLICY=/usr/share/polkit-1/actions/io.github.pokys.gnome-airdrop.policy
OWNER=$SUDO_USER
OWNER_UID=$SUDO_UID
OWNER_HOME=$(getent passwd "$OWNER_UID" | cut -d: -f6)
EXTENSION=$OWNER_HOME/.local/share/gnome-shell/extensions/gnome-airdrop@pokys.github.io
for existing in "$TARGET" "$UNIT" "$POLICY" "$EXTENSION"; do
  [[ ! -e $existing ]] || { echo "Uz existuje $existing. Nejprve pouzij odinstalaci tohoto balicku."; exit 2; }
done
for tool in python3 systemd-notify systemctl systemd-run nmcli iw ip pkexec runuser gnome-extensions restorecon xdg-user-dir openssl sysctl timeout flock ping grep awk pkill setsid; do
  command -v "$tool" >/dev/null || { echo "Chybi $tool. Instalace nic nezmeni."; exit 2; }
done
[[ -f $PACKAGE/gnome-airdrop@pokys.github.io.shell-extension.zip ]]
python3 -c 'import dbus, gi; import ctypes; ctypes.CDLL("libev.so.4"); ctypes.CDLL("libpcap.so.1"); ctypes.CDLL("libarchive.so.13"); ctypes.CDLL("libnl-3.so.200"); ctypes.CDLL("libnl-genl-3.so.200")'
[[ -z $(find "$PACKAGE/backend" -type l -print -quit) ]] || { echo 'Balicek nesmi obsahovat symlinky.'; exit 2; }
INTERFACE=${1:-}
if [[ -z $INTERFACE ]]; then
  readarray -t INTERFACES < <(iw dev | awk '$1 == "Interface" {print $2}')
  [[ ${#INTERFACES[@]} == 1 ]] || { echo 'Zadej jedno Wi-Fi rozhrani: install.sh ROZHRANI'; exit 2; }
  INTERFACE=${INTERFACES[0]}
fi
[[ $INTERFACE =~ ^[a-zA-Z0-9_.:-]+$ && -d /sys/class/net/$INTERFACE ]]
[[ $(basename "$(readlink -f "/sys/class/net/$INTERFACE/device/driver")") == iwlwifi ]] || { echo 'Tato verze podporuje pouze Intel iwlwifi.'; exit 2; }
if systemctl is-active --quiet thinkpad-airdrop.service; then
  echo 'Nejprve vypni prijem v puvodnim doplnku.'; exit 2
fi
[[ ! -d /opt/thinkpad-airdrop ]] || { echo 'Nejprve odinstaluj puvodni testovaci ThinkPad AirDrop. Prijate soubory zachovej.'; exit 2; }
DOWNLOADS=$(runuser -u "$OWNER" -- env HOME="$OWNER_HOME" xdg-user-dir DOWNLOAD)
[[ $DOWNLOADS == /* ]] || { echo 'Nelze zjistit slozku Stazene.'; exit 2; }
STAGE=$(mktemp -d /opt/.gnome-airdrop.XXXXXX)
INSTALLED=0
FINISHED=0
cleanup() {
  local rc=$?
  if [[ $FINISHED == 0 ]]; then
    echo 'Instalace nedokoncena; uklizim vytvorene soubory.'
    if [[ $INSTALLED == 1 ]]; then
      rm -f -- "$UNIT" "$POLICY"
      rm -rf -- "$TARGET"
      systemctl daemon-reload
      runuser -u "$OWNER" -- rm -rf -- "$EXTENSION"
    fi
  fi
  [[ ! -d $STAGE ]] || rm -rf -- "$STAGE"
  exit "$rc"
}
trap cleanup EXIT
cp -a "$PACKAGE/backend/." "$STAGE/"
install -m755 "$PACKAGE/uninstall.sh" "$STAGE/uninstall.sh"
chown -R root:root "$STAGE"
find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE" -type f -exec chmod 644 {} +
chmod 755 "$STAGE/uninstall.sh" "$STAGE/bin/"*.py "$STAGE/bin/listen.sh" \
  "$STAGE/lib/radio/omdrop-discoverable" "$STAGE/lib/radio/owl"
mkdir -p "$STAGE/outputs"
chmod 700 "$STAGE/outputs"
python3 - "$STAGE" "$OWNER_UID" "$OWNER" "$OWNER_HOME" "$DOWNLOADS" "$INTERFACE" <<'PY'
import json, pathlib, sys
stage, uid, name, home, downloads, interface = sys.argv[1:]
config = {'owner_uid': int(uid), 'owner_name': name, 'interface': interface,
          'user_data': str(pathlib.Path(home) / '.local/share/gnome-airdrop'),
          'download_dir': downloads}
(pathlib.Path(stage) / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
(pathlib.Path(stage) / 'INSTALLATION-MARKER').write_text('GNOME AirDrop installation v1\n')
PY
mv -- "$STAGE" "$TARGET"
INSTALLED=1
install -m644 "$PACKAGE/system/gnome-airdrop.service" "$UNIT"
install -m644 "$PACKAGE/system/io.github.pokys.gnome-airdrop.policy" "$POLICY"
restorecon -R "$TARGET" "$UNIT" "$POLICY"
systemctl daemon-reload
runuser -u "$OWNER" -- env XDG_RUNTIME_DIR="/run/user/$OWNER_UID" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$OWNER_UID/bus" \
  gnome-extensions install "$PACKAGE/gnome-airdrop@pokys.github.io.shell-extension.zip"
FINISHED=1
echo 'Nainstalovano. Prijem je vypnuty a nebude se zapinat pri startu pocitace.'
if runuser -u "$OWNER" -- env XDG_RUNTIME_DIR="/run/user/$OWNER_UID" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$OWNER_UID/bus" \
  gnome-extensions enable gnome-airdrop@pokys.github.io; then
  EXPECTED_VERSION=$(python3 - "$PACKAGE/gnome-airdrop@pokys.github.io.shell-extension.zip" <<'PYMETA'
import json, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    print(json.loads(archive.read('metadata.json'))['version'])
PYMETA
)
  LOADED_VERSION=$(runuser -u "$OWNER" -- env LC_ALL=C XDG_RUNTIME_DIR="/run/user/$OWNER_UID" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$OWNER_UID/bus" \
    gnome-extensions info gnome-airdrop@pokys.github.io 2>/dev/null | awk '$1 == "Version:" {print $2; exit}' || true)
  if [[ $LOADED_VERSION == "$EXPECTED_VERSION" ]]; then
    echo 'Rozsireni je zapnute. V horni liste hledej ikonu AirDrop.'
  else
    echo 'Soubory jsou nainstalovane, ale GNOME dosud nenacetl novy kod doplnku.'
    echo 'Po ulozeni prace se odhlas a prihlas. Pouhe vypnuti/zapnuti doplnku nestaci.'
    echo 'Pak spust: gnome-extensions enable gnome-airdrop@pokys.github.io'
  fi
else
  echo 'GNOME zatim nove rozsireni nenacetl. Po ulozeni prace se odhlas a prihlas.'
  echo 'Pak spust: gnome-extensions enable gnome-airdrop@pokys.github.io'
fi
