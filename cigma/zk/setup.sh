#!/usr/bin/env bash
# Local, single-party trusted setup for research measurements only (a production
# deployment would use a public multi-party ceremony such as the Hermez/PSE ptau files).
set -euo pipefail
S=${SNARKJS:-/tmp/zk/node_modules/.bin/snarkjs}
mkdir -p build/setup && cd build/setup
$S powersoftau new bn128 16 pot_0.ptau
$S powersoftau contribute pot_0.ptau pot_1.ptau --name="cigma-local" -e="cigma icissp 2027 research setup"
$S powersoftau prepare phase2 pot_1.ptau pot_final.ptau
$S groth16 setup ../policy.r1cs pot_final.ptau policy_0.zkey
$S zkey contribute policy_0.zkey policy.zkey --name="cigma-local-2" -e="second contribution"
$S zkey export verificationkey policy.zkey verification_key.json
echo SETUP_DONE
