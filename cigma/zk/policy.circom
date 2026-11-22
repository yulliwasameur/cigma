pragma circom 2.1.0;

// Zero-knowledge policy proof over a committed projection of the CIGMA graph.
// Each of N records describes one asset: exposed, vulnerable (quantum-vulnerable
// public-key crypto), hybrid (hybrid / PQ key establishment), highrisk (EU high-risk
// use case), plus a random salt so that the commitment hides low-entropy records.
//
// Public:  commitment (output), threshold T (input), and the two rule outcomes are implied
//          by the proof existing at all.
// Rule 1:  no asset is exposed AND vulnerable AND not hybrid       (ANSSI / EU 2030 reading)
// Rule 2:  #{assets that are highrisk AND vulnerable} <= T        (migration progress bound)

include "lib/circomlib/poseidon.circom";
include "lib/circomlib/comparators.circom";

template PolicyProof(N) {
    signal input exposed[N];
    signal input vulnerable[N];
    signal input hybrid[N];
    signal input highrisk[N];
    signal input salt[N];
    signal input threshold;
    signal output commitment;

    signal chain[N + 1];
    signal ev[N];
    signal hv[N];
    signal partial[N + 1];
    component h[N];
    chain[0] <== 0;
    partial[0] <== 0;
    for (var i = 0; i < N; i++) {
        exposed[i] * (exposed[i] - 1) === 0;
        vulnerable[i] * (vulnerable[i] - 1) === 0;
        hybrid[i] * (hybrid[i] - 1) === 0;
        highrisk[i] * (highrisk[i] - 1) === 0;
        ev[i] <== exposed[i] * vulnerable[i];
        ev[i] * (1 - hybrid[i]) === 0;                 // rule 1
        hv[i] <== highrisk[i] * vulnerable[i];
        partial[i + 1] <== partial[i] + hv[i];
        h[i] = Poseidon(6);
        h[i].inputs[0] <== chain[i];
        h[i].inputs[1] <== exposed[i];
        h[i].inputs[2] <== vulnerable[i];
        h[i].inputs[3] <== hybrid[i];
        h[i].inputs[4] <== highrisk[i];
        h[i].inputs[5] <== salt[i];
        chain[i + 1] <== h[i].out;
    }
    component le = LessEqThan(8);
    le.in[0] <== partial[N];
    le.in[1] <== threshold;
    le.out === 1;                                       // rule 2
    commitment <== chain[N];
}

component main {public [threshold]} = PolicyProof(32);
