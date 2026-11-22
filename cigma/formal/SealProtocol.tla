---------------------------- MODULE SealProtocol ----------------------------
(* Two-phase custody protocol of CIGMA's external evaluation.
   Phase 1: predictions are computed from public inputs only and sealed (digest).
   Phase 2: the oracle may be opened only after a seal, and an evaluation is run only
   if the current predictions still match the sealed digest (verify_seal.py).
   An adversary may tamper with predictions at any time.
   The hash is modelled as collision-free: digest(v) = v. *)
EXTENDS Naturals

CONSTANTS MaxV

VARIABLES phase, pred, sealed, oracleOpen, evaluated, evalPred

vars == <<phase, pred, sealed, oracleOpen, evaluated, evalPred>>
None == MaxV + 1

Init == /\ phase = "collect" /\ pred \in 0..MaxV /\ sealed = None
        /\ oracleOpen = FALSE /\ evaluated = FALSE /\ evalPred = None

Recompute == /\ phase = "collect" /\ pred' \in 0..MaxV
             /\ UNCHANGED <<phase, sealed, oracleOpen, evaluated, evalPred>>

Seal == /\ phase = "collect" /\ sealed' = pred /\ phase' = "sealed"
        /\ UNCHANGED <<pred, oracleOpen, evaluated, evalPred>>

Tamper == /\ pred' \in 0..MaxV
          /\ UNCHANGED <<phase, sealed, oracleOpen, evaluated, evalPred>>

OpenOracle == /\ phase = "sealed" /\ ~oracleOpen /\ oracleOpen' = TRUE
              /\ UNCHANGED <<phase, pred, sealed, evaluated, evalPred>>

Evaluate == /\ oracleOpen /\ ~evaluated /\ pred = sealed
            /\ evaluated' = TRUE /\ evalPred' = pred /\ phase' = "evaluated"
            /\ UNCHANGED <<pred, sealed, oracleOpen>>

Next == Recompute \/ Seal \/ Tamper \/ OpenOracle \/ Evaluate
Spec == Init /\ [][Next]_vars

TypeOK == /\ phase \in {"collect", "sealed", "evaluated"}
          /\ pred \in 0..MaxV /\ sealed \in 0..MaxV \cup {None}
          /\ oracleOpen \in BOOLEAN /\ evaluated \in BOOLEAN

NoPeek == oracleOpen => sealed # None
OnlySealedIsEvaluated == evaluated => evalPred = sealed
SealIsFinal == [][sealed # None => sealed' = sealed]_vars
=============================================================================
