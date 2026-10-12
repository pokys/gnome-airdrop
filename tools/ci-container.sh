#!/usr/bin/env bash
# For disposable CI containers only. Never install these packages on the host.
set -euo pipefail
[[ $EUID == 0 && ( -f /.dockerenv || -f /run/.containerenv ) ]] || {
  echo 'Run only inside a disposable Docker/Podman container.'; exit 2;
}
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
mkdir -p .build
dnf -q install -y gcc gcc-c++ cmake make pkgconf-pkg-config \
  libpcap-devel libev-devel libnl3-devel libarchive \
  python3 python3-dbus python3-gobject gjs openssl \
  NetworkManager iw iproute polkit systemd util-linux procps-ng iputils \
  > .build/ci-dependencies.log 2>&1 || { cat .build/ci-dependencies.log; exit 1; }
cmake -S vendor/owl -B .build/owl -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -Wno-dev
cmake --build .build/owl --target owl -j "$(nproc)"
python3 tools/package.py
# Run protocol tests without root. No Wi-Fi operation or installed service is used.
runuser -u nobody -- /bin/bash ./tools/test.sh
