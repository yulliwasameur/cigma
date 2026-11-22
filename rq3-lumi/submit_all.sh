#!/usr/bin/env bash
# Soumet un job par modèle (lit models.yaml). Budget plafonné à 40 h-nœud (journal du chantier 43).
set -euo pipefail
cd "$(dirname "$0")"
grep -E "^\s*- \{ id:" models.yaml | sed -E 's/.*id: ([^,]+), *gcd: ([0-9]+), *tp: ([0-9]+).*/\1 \2 \3/' |
while read -r id gcd tp; do sbatch --gpus-per-node="$gcd" --export=ALL,MODEL="$id",TP="$tp" run_rq3.sbatch; done
