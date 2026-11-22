#!/usr/bin/env bash
# Lot L1 — installation des outils sur macOS (Apple Silicon ou Intel).
# Prérequis : Homebrew (https://brew.sh) et Docker Desktop (ou colima) lancé.
set -euo pipefail
cd "$(dirname "$0")"
command -v brew >/dev/null || { echo "Homebrew manque : installez-le depuis https://brew.sh puis relancez ce script."; exit 1; }
brew install kind kubectl helm istioctl jq yq syft step git python@3.11
python3.11 -m venv .venv && .venv/bin/pip install -q "sslyze==6.*" pyyaml cryptography   # environnement isolé (le Python de Homebrew refuse pip --user)
docker info >/dev/null || { echo "Docker n'est pas lancé : ouvrez Docker Desktop (4 CPU, 8 Go de RAM minimum)"; exit 1; }
mkdir -p ../docs
{
  echo "# Versions des outils (relevées par setup_mac.sh le $(date -u +%FT%TZ))"
  echo "- kind : $(kind version 2>/dev/null)"
  echo "- kubectl : $(kubectl version --client 2>/dev/null | head -1)"
  echo "- helm : $(helm version --short 2>/dev/null)"
  echo "- istioctl : $(istioctl version --remote=false 2>/dev/null | head -1)"
  echo "- syft : $(syft version 2>/dev/null | grep -i '^Version' | head -1)"
  echo "- step : $(step version 2>/dev/null | head -1)"
  echo "- jq : $(jq --version 2>/dev/null)"
  echo "- sslyze : $(.venv/bin/python -m sslyze --help 2>/dev/null | head -1)"
  echo "- docker : $(docker version --format '{{.Server.Version}}')"
} > ../docs/VERSIONS-L1-TOOLS.md
echo "Outils installés. Versions écrites dans docs/VERSIONS-L1-TOOLS.md"
