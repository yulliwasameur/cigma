#!/usr/bin/env bash
# Prove and verify the policy for each scenario; record times and outcomes.
S=${SNARKJS:-/tmp/zk/node_modules/.bin/snarkjs}
cd build
echo "scenario,witness_ok,prove_seconds,verify_ok,verify_seconds,proof_bytes" > zk_results.csv
for sc in current after_plan after_plan_tight; do
  if node policy_js/generate_witness.js policy_js/policy.wasm input_$sc.json w_$sc.wtns >/dev/null 2>&1; then
    t0=$(date +%s.%N); $S groth16 prove setup/policy.zkey w_$sc.wtns proof_$sc.json public_$sc.json >/dev/null; t1=$(date +%s.%N)
    if $S groth16 verify setup/verification_key.json public_$sc.json proof_$sc.json 2>&1 | grep -q "OK"; then v=true; else v=false; fi; t2=$(date +%s.%N)
    echo "$sc,true,$(echo "$t1-$t0"|bc),$v,$(echo "$t2-$t1"|bc),$(wc -c < proof_$sc.json)" >> zk_results.csv
  else
    echo "$sc,false,,,," >> zk_results.csv
  fi
done
cat zk_results.csv
