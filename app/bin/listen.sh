#!/usr/bin/env bash
# First test: radio on/off only. No package installation or persistent config.
set -euo pipefail
TASK_DIR=$(cd -- "$(dirname -- "$0")/.." && pwd)
HELPER=$TASK_DIR/lib/radio/omdrop-discoverable
STA=${AIR_DROP_INTERFACE:?Missing wireless interface}
RECEIVED_DIR=${AIR_DROP_RECEIVED_DIR:?Missing download directory}
USER_DATA=${AIR_DROP_USER_DATA:?Missing user data directory}
umask 077
MODE=${1:-smoke}
case "$MODE" in
  smoke) WINDOW=15; WATCH=15; GUARD_SECONDS=75 ;;
  --discover) WINDOW=30; WATCH=30; GUARD_SECONDS=90 ;;
  --receive) WINDOW=30; WATCH=30; GUARD_SECONDS=90 ;;
  --listen) WINDOW=0; WATCH=0; GUARD_SECONDS=90 ;;
  *) echo "Pouziti: sudo bash $0 [--discover|--receive|--listen]"; exit 2 ;;
esac
[[ $EUID == 0 ]] || { echo "Spustit pres sudo bash $0"; exit 2; }
for tool in iw nmcli ip sysctl timeout flock systemd-run systemctl ping grep awk python3 pkill setsid; do
  command -v "$tool" >/dev/null || { echo "Chybi potrebny prikaz: $tool; test nespoustim."; exit 2; }
done
[[ -x $HELPER ]] || { echo 'Backend neni sestaveny.'; exit 2; }
if [[ $MODE == --receive || $MODE == --listen ]]; then
  [[ -n ${SUDO_USER:-} && ${SUDO_UID:-0} != 0 ]] || { echo 'Prijimac musi byt spusten pomoci sudo z bezneho uzivatele.'; exit 2; }
  command -v runuser >/dev/null
  runuser -u "$SUDO_USER" -- env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$TASK_DIR/lib/python" \
    python3 "$TASK_DIR/lib/receiver/airdrop-serve.py" --help >/dev/null
fi
[[ $(basename "$(readlink -f "/sys/class/net/$STA/device/driver")") == iwlwifi ]]
iw dev "$STA" info | grep -q 'type managed'
[[ $(nmcli -g GENERAL.STATE device show "$STA") == 100* ]] || { echo 'Wi-Fi musi byt na zacatku pripojena.'; exit 2; }
for iface in mon0 awdl0 awdlibss0; do
  if ip link show "$iface" >/dev/null 2>&1; then echo "Rozhrani $iface uz existuje; test nespoustim."; exit 2; fi
done
if [[ -e /run/omdrop-owl ]]; then echo 'Existuje stav jineho omdrop; test nespoustim.'; exit 2; fi
STATE=$(mktemp -d /run/gnome-airdrop/session.XXXXXX)
printf '%s\n' "$STATE" > /run/gnome-airdrop/current
chmod 700 "$STATE"
export OMDROP_RUN=$STATE/backend OMDROP_CONF=$STATE/config
mkdir "$OMDROP_CONF"
printf '%s\n' "$STA" > "$OMDROP_CONF/infra-iface"
if [[ $MODE == --receive || $MODE == --discover || $MODE == --listen ]]; then
  # Use the AX211 station-conversion path already supported by upstream.
  printf '1\n' > "$OMDROP_CONF/force-station"
fi
nmcli -g GENERAL.CON-UUID device show "$STA" > "$STATE/uuid"
sysctl -n "net.ipv6.conf.$STA.disable_ipv6" > "$STATE/ipv6"
ip -4 route show default dev "$STA" | awk '{print $3; exit}' > "$STATE/gateway"
cat > "$STATE/recover.sh" <<'RECOVER'
#!/usr/bin/env bash
set -u
STATE=$1 HELPER=$2 STA=$3
exec 8> "$STATE/recover.lock"
flock -w 60 8 || exit 1
export OMDROP_RUN=$STATE/backend OMDROP_CONF=$STATE/config
for kind in receiver ble; do
  pid=$(cat "$STATE/$kind.pid" 2>/dev/null || true)
  if [[ $pid =~ ^[0-9]+$ ]] && [[ -r /proc/$pid/cmdline ]]; then
    if tr '\0' ' ' < "/proc/$pid/cmdline" | grep -qF '/opt/gnome-airdrop/lib/'; then
      kill -- "-$pid" 2>/dev/null || true
    fi
  fi
done
timeout -k 3 12 "$HELPER" stop || true
# Kill only this test's processes if the upstream stop stalled.
for kind in supervisor owl; do
  pid=$(cat "$OMDROP_RUN/$kind.pid" 2>/dev/null || true)
  if [[ $pid =~ ^[0-9]+$ ]] && [[ -r /proc/$pid/cmdline ]]; then
    if tr '\0' ' ' < "/proc/$pid/cmdline" | grep -qF "$(dirname "$HELPER")/"; then
      kill "$pid" 2>/dev/null || true
    fi
  fi
done
for iface in mon0 awdlibss0; do iw dev "$iface" del 2>/dev/null || true; done
if ! iw dev "$STA" info | grep -q 'type managed'; then
  iw dev "$STA" ibss leave 2>/dev/null || true
  ip link set "$STA" down
  iw dev "$STA" set type managed || exit 1
fi
sysctl -qw "net.ipv6.conf.$STA.disable_ipv6=$(cat "$STATE/ipv6")"
ip link set "$STA" up
nmcli device set "$STA" managed yes
if [[ $(nmcli -g GENERAL.STATE device show "$STA") != 100* ]]; then
  nmcli -w 30 connection up uuid "$(cat "$STATE/uuid")" ifname "$STA"
fi
[[ $(nmcli -g GENERAL.STATE device show "$STA") == 100* ]]
RECOVER
chmod 700 "$STATE/recover.sh"
GUARD=gnome-airdrop-guard-$$
printf '%s\n' "$GUARD" > "$STATE/guard"
systemd-run --quiet --collect --unit "$GUARD" --on-active="${GUARD_SECONDS}s" \
  --timer-property=AccuracySec=1s \
  /bin/bash "$STATE/recover.sh" "$STATE" "$HELPER" "$STA"
cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  if bash "$STATE/recover.sh" "$STATE" "$HELPER" "$STA"; then
    systemctl stop "$GUARD.timer" 2>/dev/null || true
    systemctl stop "$GUARD.service" 2>/dev/null || true
    mkdir -p "$TASK_DIR/outputs"
    if [[ -f $OMDROP_RUN/log ]]; then
      cp "$OMDROP_RUN/log" "$TASK_DIR/outputs/radio-smoke-backend.log"
      chmod 600 "$TASK_DIR/outputs/radio-smoke-backend.log"
    fi
    for logfile in owl.log announce.log ibss-link.log; do
      if [[ -f $OMDROP_RUN/$logfile ]]; then
        cp "$OMDROP_RUN/$logfile" "$TASK_DIR/outputs/radio-smoke-$logfile"
        chmod 600 "$TASK_DIR/outputs/radio-smoke-$logfile"
      fi
    done
    rm -rf -- "$STATE"
    echo 'Wi-Fi obnovena.'
  else
    echo "Obnova se nepodarila. Pojistka zustava aktivni. Rucni obnova: sudo bash $STATE/recover.sh $STATE $HELPER $STA"
    exit 1
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo 'Kontrola backendu:'
[[ $("$HELPER" probe) == ready ]] || { "$HELPER" probe; exit 1; }
if [[ $MODE == --listen ]]; then
  echo 'Zapinam AirDrop do Ctrl+C. Bezna Wi-Fi bude po dobu prijmu odpojena.'
else
  echo "Zapinam radio nejvyse na $WINDOW sekund; Wi-Fi bude docasne odpojena."
fi
if ! timeout -k 3 45 "$HELPER" start "$WINDOW" > "$TASK_DIR/outputs/radio-start.log" 2>&1; then
  cat "$TASK_DIR/outputs/radio-start.log"
  echo 'Start radia selhal; prijimac nebyl spusten. Obnovuji Wi-Fi.'
  exit 1
fi
cat "$TASK_DIR/outputs/radio-start.log"
"$HELPER" status --json
if [[ $MODE == --receive || $MODE == --listen ]]; then
  PROCESS_LIMIT=(timeout -k 3 35)
  BLE_SECONDS=30
  if [[ $MODE == --listen ]]; then PROCESS_LIMIT=(); BLE_SECONDS=0; fi
  setsid "${PROCESS_LIMIT[@]}" runuser -u "$SUDO_USER" -- env \
    PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONPATH="$TASK_DIR/lib/python" \
    XDG_CONFIG_HOME="$USER_DATA/config" XDG_RUNTIME_DIR="$USER_DATA/runtime" \
    GNOME_AIRDROP_EVENT_FILE="$USER_DATA/runtime/receipt.json" \
    python3 -u "$TASK_DIR/lib/receiver/airdrop-serve.py" \
    --name GNOME-AirDrop --keys "$USER_DATA/identity" \
    --config "$USER_DATA/config/receiver.toml" --outdir "$RECEIVED_DIR" \
    > "$TASK_DIR/outputs/receiver.log" 2>&1 < /dev/null &
  echo $! > "$STATE/receiver.pid"
  setsid "${PROCESS_LIMIT[@]}" python3 -u "$(dirname "$HELPER")/ble-airdrop-adv.py" \
    --hashes 0000000000000000 --seconds "$BLE_SECONDS" --interval-ms 100 \
    > "$TASK_DIR/outputs/bluetooth.log" 2>&1 < /dev/null &
  echo $! > "$STATE/ble.pid"
  sleep 1
  if [[ $MODE != --listen ]]; then
    cat "$TASK_DIR/outputs/receiver.log"
    cat "$TASK_DIR/outputs/bluetooth.log"
  fi
  if ! grep -q 'serving .*_airdrop._tcp.local' "$TASK_DIR/outputs/receiver.log"; then
    cat "$TASK_DIR/outputs/receiver.log"
    echo 'Prijimac nenastartoval; ukoncuji test a obnovuji Wi-Fi.'
    exit 1
  fi
  echo "Prijimac GNOME-AirDrop je spusten. Soubory: $RECEIVED_DIR"
fi
if [[ $MODE == --listen ]]; then
  systemd-notify --ready
  echo 'Prijem zapnuty. Vypnuti pres prepinac v GNOME.'
  # Restarting this independent timer gives the parent 90 seconds to check
  # in again. If it crashes or hangs, the timer restores the original Wi-Fi.
  while true; do
    sleep 10
    # A graphical Shell restart keeps the user active; logout or switching
    # away from this user's active seat ends receiving.
    if [[ $(loginctl show-user "$SUDO_UID" --property=State --value) != active ]]; then
      echo 'Uzivatel uz neni aktivni; obnovuji Wi-Fi.'
      exit 0
    fi
    for kind in receiver ble; do
      pid=$(cat "$STATE/$kind.pid")
      if ! kill -0 "$pid" 2>/dev/null; then
        echo "Proces $kind skoncil; ukoncuji prijem a obnovuji Wi-Fi."
        exit 1
      fi
    done
    if ! "$HELPER" status --json | grep -q '"visible":true'; then
      echo 'Radio prestalo odpovidat; obnovuji Wi-Fi.'
      exit 1
    fi
    systemctl restart "$GUARD.timer"
  done
fi
echo "Sleduji komunikaci s iPhonem $WATCH sekund (Ctrl-C spusti obnovu)."
for ((elapsed=0; elapsed<WATCH; elapsed+=5)); do
  sleep 5
  "$HELPER" status --json
  "$HELPER" peers || true
done
"$HELPER" peers || true
bash "$STATE/recover.sh" "$STATE" "$HELPER" "$STA"
systemctl stop "$GUARD.timer" 2>/dev/null || true
GW=$(cat "$STATE/gateway")
[[ -n $GW ]] || { echo 'Chybi puvodni brana; nelze otestovat provoz.'; exit 1; }
echo 'Kontroluji Wi-Fi po dobu 5 minut.'
ping -I "$STA" -c 60 -i 5 -W 2 "$GW"
if [[ $MODE == --receive ]]; then
  echo 'Test dokoncen. Prijate soubory: outputs/received; log prijimace: outputs/receiver.log.'
else
  echo 'Test dokonceny. Zadny soubor se neprenasel.'
fi
echo 'Docasny stav bude uklizen; log zustane v outputs/radio-smoke-backend.log.'
