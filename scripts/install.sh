#!/bin/sh
# One-shot install on a fresh Linux box (Debian/Ubuntu/WSL). Run as a normal user:
#   sh scripts/install.sh
# Then put your keys in .secrets/env (see .secrets.example) and run:  sh scripts/run.sh
set -e
cd "$(dirname "$0")/.."
command -v python3 >/dev/null || { echo "python3 missing: sudo apt install -y python3"; exit 1; }
mkdir -p .secrets state/logs release
[ -f .secrets/env ] || { cp .secrets.example .secrets/env; chmod 600 .secrets/env; echo "created .secrets/env - fill in your keys"; }
chmod 700 .secrets
python3 -m agent.selfcheck
echo "install OK. start with:  sh scripts/run.sh   (or install the service: sh scripts/service.sh)"
