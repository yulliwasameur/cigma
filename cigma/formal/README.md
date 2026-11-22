# Formal model of the custody (seal) protocol

`SealProtocol.tla` models the two-phase external evaluation: predictions are sealed
before the oracle can be opened, an adversary may tamper with predictions at any
time, and `verify_seal.py` refuses to evaluate unless the predictions still match
the seal. The hash is modelled as collision-free.

Checked properties (TLC, MaxV = 3: 252 states generated, 52 distinct, no error):
- `NoPeek`: the oracle is never opened before a seal exists;
- `OnlySealedIsEvaluated`: what is evaluated is exactly what was sealed, whatever the adversary did;
- `SealIsFinal` (temporal): once set, the seal never changes;
- `TypeOK`.

Run: `java -cp tla2tools.jar tlc2.TLC -config SealProtocol.cfg SealProtocol.tla`
(tla2tools v1.8.0 from https://github.com/tlaplus/tlaplus/releases).
