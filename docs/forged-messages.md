# Forged and malformed messages

A review of the C code found that the detector and controller trusted any message: no length check, and no check of who sent it.
This page records what was changed, what was not, and the test on QNX. The expectations below were written before the runs.

## What was changed
Both receivers now check the message length (`_msg_info.msglen`) and reject a short message with `MsgError(EBADMSG)` instead
of reading stale fields from the previous message (`pipeline/detector.c`, `pipeline/controller.c`).

## What was not changed, on purpose
Our pipeline does not check who sent a message. Any process that can connect to the detector can send a well-formed frame with any
sequence number, or a stop message, and the pipeline believes it. QNX gives a server the sender's identity in the receive
(`_msg_info.pid`, `scoid`, and `ConnectClientInfo` for user and group ids), and a client cannot forge it, so a server **should** check it; we did
not implement that. The other QNX answer is a security policy that decides **who may connect at all**, which is what the
`secpol-connect` profile does ([`security-policy.md`](security-policy.md)).

## The test (`examples/forge/siege.json`, attacker mode `forge`)
| Scenario | none | secpol-connect | secpol-lockdown |
|---|---|---|---|
| forge: short messages (`FORGE=short`) | expect pass: the length checks reject them | pass | pass |
| forge: one bogus sequence number (`FORGE=seq`) | expect **fail**: the controller's loss accounting breaks | pass: the attacker cannot connect | pass |

## Result (QEMU, 10 runs per cell)

| Scenario | none | secpol-connect | secpol-lockdown |
|---|---|---|---|
| forge: short messages | 1/10 failed | 0/10 failed | 0/10 failed |
| forge: one bogus sequence number | 10/10 failed | 0/10 failed | 0/10 failed |

All four predictions held: the length checks absorbed the short messages (one failed run in ten is the noise level seen with no attacker),
one forged sequence number broke the unprotected pipeline every time, and both policy profiles stopped it because the attacker could not
connect. The forged sequence number is an attack the pipeline cannot defend against by itself as written; a sender-identity check
(see above) is not implemented. Raw data: [`examples/forge/results/`](../examples/forge/results/).

A forged stop message (which ends the run early and can make a truncated run look like a pass) is a known weakness and is
not part of this matrix.
