#!/usr/bin/env bash
# Compilers and development packages stay in a disposable rootless container.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
[[ $EUID != 0 ]] || { echo 'Build as an ordinary user, without sudo.'; exit 2; }
command -v podman >/dev/null
command -v python3 >/dev/null
mkdir -p "$ROOT/.build"
BUILD_RUNTIME=$(mktemp -d /tmp/gnome-airdrop-build.XXXXXX)
STORAGE=$(mktemp -d "$ROOT/.build/storage.XXXXXX")
cleanup() {
  podman --root "$STORAGE" --runroot "$BUILD_RUNTIME" --storage-driver vfs unshare rm -rf -- "$STORAGE"
  rm -rf -- "$STORAGE" "$BUILD_RUNTIME"
}
trap cleanup EXIT
podman --root "$STORAGE" --runroot "$BUILD_RUNTIME" --storage-driver vfs run --rm \
  --security-opt label=disable -v "$ROOT:/project:rw" -w /project \
  registry.fedoraproject.org/fedora:44 bash -euc '
    dnf -q install -y gcc gcc-c++ cmake make pkgconf-pkg-config libpcap-devel libev-devel libnl3-devel
    cmake -S vendor/owl -B .build/owl -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -Wno-dev
    cmake --build .build/owl --target owl -j "$(nproc)"
  '
python3 "$ROOT/tools/package.py"
