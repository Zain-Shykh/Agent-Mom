# Known Limitations (Part 2 → Part 3/4 handoff)

Observed behavior from building and manually verifying Part 2
(`docs/implementation_plan.md` Phases 1–14), mapped against the `(c)
unsupported` AI-assumption rows in
`docs/Part1_Requirement_Scope_and_AI_Assumptions.md`. This is the direct
input for Part 3's functional test derivation and Part 4's defect log —
none of the items below were "fixed" before hand-off; each is implemented
as-is and made observable via the log panel, per `docs/architecture.md`
§10.

## The 7 `(c) unsupported` assumptions — as actually observed

1. **Multicast join/leave timing** (3.2.2.3–3.2.2.6) — confirmed non-synchronous. In the Phase 3 standalone test, a member that called `leave_group()` and got the call back still received a message sent immediately after. In the Phase 14 GUI run, the same scenario did *not* reproduce (the post-leave message was not received) — i.e. the behavior is genuinely timing-dependent/non-deterministic, not a fixed bug with one direction. Report as: delivery after `leave_group()` returns is unreliable in either direction.

2. **Multicast config validation strictness** (3.2.2.1, 3.2.2.2, 3.2.2.7–3.2.2.9) — no validation beyond what the OS itself enforces. `TTL=0` was accepted silently and did not error (message stayed host-local, as expected for TTL 0). `TTL=999` (outside the valid 0–255 byte range for `IP_MULTICAST_TTL`) was **not** pre-validated by the app — it reached `setsockopt()` and the OS raised `OSError: [Errno 22] Invalid argument`. No multicast-address-range check exists either (e.g. a non-multicast address typed into the Group panel would be accepted by the UI and only fail, if at all, at the OS level).

3. **Broadcast permission bypass** (3.2.3.1, 3.2.3.2, 3.3.3.3) — no OS-permission pre-check exists in `broadcast.py`. Not observed to fail in this environment (broadcast succeeded on every Phase 4/14 run), consistent with the assumption being untested across environments rather than proven safe — Part 3 should test on a more restrictive network/OS if possible.

4. **Encryption algorithm/key choice** (3.2.4.1–3.2.4.6) — AES-256-GCM via the `cryptography` library, one symmetric key generated once per process and shared in-memory across all `AgentNode`s (`main.py`). No key rotation, no out-of-band distribution — this stands in for the SRS's conceptual "key-distribution agent" and was never a claim of real key management.

5. **Reliability / silent-failure handling** (§2.4.1) — **this one was actually caught during the Part 2 build itself, not left for Part 3 to discover.** As initially implemented (through Phase 13), `AgentNode.send()` had no path to the log panel for a failed delivery at all — exactly the AI-introduced gap Part 1 predicted ("may silently swallow delivery failures instead of surfacing them to the sender"). It surfaced during Phase 14 checklist item 7 (send to a closed port) as a bare `ConnectionRefusedError` with no `ERROR` log line. Since `architecture.md` §10 explicitly calls for "delivery failures logged, not retried or acknowledged" as the *intended* design (not one of the defects to leave alone), this was fixed: `AgentNode.send()` now pushes an `error` Event before re-raising. Worth recording in Part 4 regardless — the predicted defect really did occur once, briefly, during development.

6. **Security strength dependency** (§2.4.2) — no independent verification that AES-256-GCM as wired here is actually safe against a knowledgeable attacker (e.g. nonce reuse under key rotation was never exercised, since there is no key rotation). Flag for Part 3's SonarQube pass.

7. **Portability / single-environment validation** (§2.4.3 / §2.4.4) — every phase above was verified on exactly one Linux machine, over loopback (`127.0.0.1`) and one local subnet. No multi-machine, multi-NIC, or restrictive-firewall environment was tested. Report as an explicit scope limitation, not a pass.

## Other bugs found and fixed during the Part 2 build (not `(c)`-flagged AI assumptions)

These are implementation bugs unrelated to the Part 1 assumption table — genuine defects in the socket lifecycle code, caught and fixed before hand-off because they broke the app's own teardown, not because they were part of the SRS's uncertain scope:

- **Listener threads never actually died.** `UnicastTransport`, `MulticastTransport`, and `BroadcastTransport` all blocked their accept/recv loops on the raw blocking socket call, relying on another thread's `close()` to unblock them — on Linux this is not reliable. `stop()`/`leave_group()` could return while the thread was still alive and the port still bound, breaking re-use of the same port (surfaced first as `AgentNode` re-creation failing with "Address already in use" in the Phase 8 pytest suite). Fixed with a 0.5s `settimeout()` on each socket so the loops poll their stop flag instead of blocking forever.

## `agent_core/` has no `tkinter` dependency

```
$ grep -rn "tkinter" agent_core/
(no output)
```

Confirmed clean — `agent_core/` stays independently unit-testable for Part 3's SonarQube run and functional tests, with no GUI dependency.
