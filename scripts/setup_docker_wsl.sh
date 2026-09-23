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
set -euo pipefail

echo "==> 1/4  Docker Engine"
if command -v docker >/dev/null 2>&1; then
    echo "    already installed: $(docker --version)"
else
    curl -fsSL https://get.docker.com | sudo sh
fi

echo "==> 2/4  Add $USER to the docker group (no sudo for docker afterwards)"
sudo usermod -aG docker "$USER"

echo "==> 3/4  Start the daemon"
# WSL images often ship without systemd; `service` works either way.
sudo service docker start || true

echo "==> 4/4  gVisor (runsc)"
# No account, no licence key -- it is an Apache-2.0 binary from Google.
if command -v runsc >/dev/null 2>&1; then
    echo "    already installed: $(runsc --version | head -1)"
else
    sudo apt-get update -qq
    sudo apt-get install -y -qq apt-transport-https ca-certificates curl gnupg
    curl -fsSL https://gvisor.dev/archive.key \
        | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" \
        | sudo tee /etc/apt/sources.list.d/gvisor.list > /dev/null
    sudo apt-get update -qq
    sudo apt-get install -y runsc
fi

# Register runsc as a Docker runtime. --experimental picks the systrap platform,
# which needs no KVM -- WSL2 does not expose nested virtualisation.
sudo runsc install
sudo service docker restart || true

echo
echo "================================================================"
echo "Done. Open a NEW wsl shell so the docker group applies, then:"
echo
echo "    docker run --rm hello-world"
echo "    docker run --rm --runtime=runsc alpine dmesg | head -3"
echo
echo "The second should print a gVisor banner rather than a Linux one."
echo "================================================================"
