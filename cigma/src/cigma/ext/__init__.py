"""ICISSP 2027 extensions of the CIGMA clean-room implementation.

Each module adds one capability without changing the deterministic core:

- ``reliability``: source reliabilities learned without ground truth (truth discovery),
  with detection of sources that copy each other;
- ``multitool``: several disagreeing generators inside one source family (e.g. CBOM tools);
- ``ordering``: interoperability-aware migration order, MOVR and exposure metrics,
  and a machine-checkable plan certificate;
- ``exposure``: separate harvest-now-decrypt-later (confidentiality) and
  trust-now-forge-later (authenticity) exposure under an uncertain quantum-arrival date;
- ``hybrid``: hybrid and post-quantum key-establishment groups seen on real endpoints;
- ``consensus``: k-of-n agreement across several language models, behind the validator;
- ``commitment``: Merkle commitment of the graph with per-decision inclusion proofs;
- ``active``: budgeted choice of which uncertain edges a human should verify first.
"""
