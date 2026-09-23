#!/usr/bin/env bash
# Install Docker Engine + gVisor inside WSL2 Ubuntu.
#
# Run this yourself in a WSL terminal -- it needs sudo:
#     wsl -d Ubuntu
#     bash /mnt/c/Users/anand/Downloads/ORION/scripts/setup_docker_wsl.sh
#
# Docker Desktop is deliberately not used: it needs Windows admin, and a Docker
# Engine inside WSL is a real Linux daemon, which is what ORION actually deploys
# against. It also lets gVisor be tested here rather than only in production.
#
# Idempotent -- re-running skips whatever is already installed.
set -euo pipefail

# --- helpers --------------------------------------------------------------

# unattended-upgrades runs on every WSL boot and holds the dpkg lock for a few
# minutes. A script that dies on that is a script you have to babysit.
wait_for_dpkg() {
    local waited=0
    while sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
        if [ "$waited" -eq 0 ]; then
            echo "    waiting for another package manager (unattended-upgrades) to finish..."
        fi
        sleep 5
        waited=$((waited + 5))
        if [ "$waited" -ge 600 ]; then
            echo "    still locked after 10 minutes; giving up." >&2
            return 1
        fi
    done
    [ "$waited" -gt 0 ] && echo "    lock released after ${waited}s"
    return 0
}

echo "==> 1/4  Docker Engine"
if command -v docker >/dev/null 2>&1; then
    echo "    already installed: $(docker --version)"
else
    wait_for_dpkg
    curl -fsSL https://get.docker.com | sudo sh
fi

echo "==> 2/4  Add $USER to the docker group (no sudo for docker afterwards)"
sudo usermod -aG docker "$USER"

echo "==> 3/4  Start the daemon"
# WSL images often ship without systemd; `service` works either way.
sudo service docker start >/dev/null 2>&1 || true

echo "==> 4/4  gVisor (runsc)"
# No account, no licence key -- Apache-2.0 binaries published by Google.
#
# Installed from the release bucket rather than the apt repo: apt needs the dpkg
# lock, which unattended-upgrades holds on every fresh WSL boot, and that is what
# blocked this step the first time. The download is checksum-verified, which is
# the property that actually matters.
#
# gVisor ships a tarball, not bare binaries -- an earlier version of this script
# fetched .../x86_64/runsc directly and got four 404s. The archive also contains
# a gvisor-bin/ directory of helpers that runsc needs at runtime, so all three
# entries are installed, not just the two executables.
if command -v runsc >/dev/null 2>&1; then
    echo "    already installed: $(runsc --version | head -1)"
else
    ARCH="$(uname -m)"
    URL="https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}"
    WORK="$(mktemp -d)"
    trap 'rm -rf "$WORK"' EXIT

    echo "    downloading gvisor for ${ARCH} (~166 MB)"
    curl -fsSL -o "$WORK/gvisor.tar.bz2"        "${URL}/gvisor.tar.bz2"
    curl -fsSL -o "$WORK/gvisor.tar.bz2.sha512" "${URL}/gvisor.tar.bz2.sha512"

    echo "    verifying checksum"
    ( cd "$WORK" && sha512sum -c gvisor.tar.bz2.sha512 )

    # A minimal Ubuntu has neither bzip2 nor zstd, and installing one would mean
    # apt -- the thing this step exists to avoid. Python's stdlib decompresses
    # both, and python3 is always present.
    echo "    extracting"
    mkdir -p "$WORK/x"
    python3 - "$WORK/gvisor.tar.bz2" "$WORK/x" <<'PY'
import sys, tarfile

archive, destination = sys.argv[1], sys.argv[2]
with tarfile.open(archive, "r:bz2") as tar:
    try:
        # Refuses paths escaping the destination. Added in 3.11.4/3.12; the
        # archive is checksum-verified either way, this is belt and braces.
        tar.extractall(destination, filter="data")
    except TypeError:
        tar.extractall(destination)
PY

    sudo cp -a "$WORK/x/runsc" "$WORK/x/containerd-shim-runsc-v1" \
               "$WORK/x/gvisor-bin" /usr/local/bin/
    sudo chown -R root:root /usr/local/bin/runsc \
                            /usr/local/bin/containerd-shim-runsc-v1 \
                            /usr/local/bin/gvisor-bin
    sudo chmod 0755 /usr/local/bin/runsc /usr/local/bin/containerd-shim-runsc-v1

    echo "    installed: $(/usr/local/bin/runsc --version | head -1)"
fi

echo "==> Registering runsc as a Docker runtime"
# `runsc install` writes /etc/docker/daemon.json. The default platform is
# systrap, which needs no KVM -- WSL2 exposes no nested virtualisation.
sudo /usr/local/bin/runsc install
sudo service docker restart >/dev/null 2>&1 || sudo systemctl restart docker || true
sleep 3

echo
echo "================================================================"
if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q runsc; then
    echo "runsc is registered with Docker."
else
    echo "WARNING: docker does not list runsc as a runtime yet."
    echo "Try: sudo systemctl restart docker"
fi
echo
echo "Open a NEW wsl shell so the docker group applies, then check:"
echo
echo "    docker run --rm hello-world"
echo "    docker run --rm --runtime=runsc alpine dmesg | head -3"
echo
echo "The second should mention gVisor rather than a stock Linux kernel."
echo "================================================================"
