# Part 3(b) — Functional Test Derivation, Execution and Traceability

**Scope tested:** the 7 FRs from `docs/Part1_Requirement_Scope_and_AI_Assumptions.md`, against the frozen baseline in `agent_core/` + `agent_gui/` (application code frozen at commit `09403cc` — verified unchanged through every later commit, including this test/evidence work).

**Execution method:** TC-01–TC-12 were executed against `agent_core/` directly (real sockets, real threads, no GUI) using `tests/part3b_extra_tests.py` and the existing `tests/smoke_test_core.py`, run with `pytest`. `agent_core/` has no `tkinter` dependency and is independently testable at this layer (confirmed in `KNOWN_LIMITATIONS.md`). TC-13–TC-15 are system-level tests and were executed manually against the running GUI (`main.py`), consistent with the assignment's requirement that system-level cases be executed by a person rather than automated.

---

## Table A — Test Condition Record

| Test basis / requirement | Condition ID | Test condition |
|---|---|---|
| R1 — Unicast (3.2.1.1–3.2.1.4) | COND-01 | Message sent to a specific agent address is received only by that agent |
| R1 — Unicast (3.2.1.1–3.2.1.4) / NFR-Reliability (§2.4.1) | COND-02 | Delivery failure (unreachable target) is surfaced as an error, not silently swallowed |
| R2 — Multicast membership (3.2.2.3–3.2.2.6) | COND-03 | Agent that joined a group receives messages sent to it |
| R2 — Multicast membership (3.2.2.3–3.2.2.6) | COND-04 | Agent must NOT receive a group message sent immediately after it left the group |
| R3 — Multicast msg/config (3.2.2.1,3.2.2.2,3.2.2.7–3.2.2.9) | COND-05 | TTL at the minimum valid value (1) is accepted and message delivered |
| R3 — Multicast msg/config | COND-06 | TTL at the maximum valid value (255, the `IP_MULTICAST_TTL` byte ceiling) is accepted and delivered |
| R3 — Multicast msg/config | COND-07 | TTL outside the valid range (too high, negative) is rejected with a graceful, user-visible error |
| R3 — Multicast msg/config | COND-08 | A non-multicast address entered as the group address is rejected before sending |
| R3 — Multicast msg/config | COND-09 | An agent subscribed to 2+ groups receives messages from each independently |
| R4 — Broadcast (3.2.3.1,3.2.3.2,3.3.3.3) | COND-10 | A broadcast message is received by every other agent on the local network |
| R5 — Security (3.2.4.1–3.2.4.6) | COND-11 | An encrypted message is automatically decrypted correctly by the recipient |
| R5 — Security (3.2.4.1–3.2.4.6) / NFR-Security (§2.4.2) | COND-12 | A message that cannot be decrypted (wrong key/tampered) is handled gracefully, not a crash |
| R2 + R3 (system-level) | COND-13 | End-to-end: join a group via the GUI, send a multicast via the GUI, see it arrive in the recipient's log panel |
| R6 — Conversation architecture (3.2.5.1/3.2.5.2) | COND-14 | Switching an agent's conversation-control mode in the GUI visibly changes its behaviour (auto-ack vs. silent) |
| R7 — Mode selection (§2.2.4) | COND-15 | The GUI's mode selector correctly routes a message through unicast, multicast, and broadcast in turn |

---

## Table B — Test Case Record

### TC-01 — Unicast normal delivery
- **Level/category:** Normal, automated (core-layer)
- **Test basis:** COND-01 / SRS 3.2.1.3 ("Unicast message shall only be received by the specified address")
- **Preconditions:** Two `AgentNode`s running, N1 on port 7501, N2 on port 7502
- **Test data:** payload `"hello N2"`, target `127.0.0.1:7502`
- **Steps:** N1.send("unicast", target, "hello N2") → poll N2's events
- **Expected result:** N2's event queue contains a `received` event with the payload
- **Actual result:** N2 received exactly the sent payload
- **Status:** **PASSED**
- **Evidence:** `tests/smoke_test_core.py::test_unicast_delivery_and_no_autonomous_reaction` — pytest run, 5 passed in 11.86s (full session log retained)

### TC-02 — Unicast to an unreachable port surfaces an error, not silence
- **Level/category:** Invalid/error
- **Test basis:** COND-02 / NFR-Reliability §2.4.1, and `KNOWN_LIMITATIONS.md` item 5 (this exact gap was found and fixed during Part 2)
- **Preconditions:** N1 running; no listener on port 7899
- **Test data:** target `127.0.0.1:7899`, payload `"into the void"`
- **Steps:** N1.send("unicast", "127.0.0.1:7899", "into the void") → poll N1's own events
- **Expected result:** `ConnectionRefusedError` propagates AND an `error` Event is queued for the log panel (per architecture.md §10 — "logged, not retried or acknowledged")
- **Actual result:** Both occurred exactly as expected — exception raised, `error` Event present
- **Status:** **PASSED**
- **Evidence:** `tests/part3b_extra_tests.py::test_unicast_to_closed_port_logs_error_event` — pytest PASSED

### TC-03 — Multicast join then receive
- **Level/category:** Normal, automated
- **Test basis:** COND-03 / SRS 3.2.2.5 (implicitly — receipt requires membership)
- **Preconditions:** N2, N3 join group `239.9.9.9:7700`
- **Test data:** payload `"group hello"`
- **Steps:** N1.send("multicast", ...) → poll N2 and N3
- **Expected result:** both N2 and N3 receive the message
- **Actual result:** both received it
- **Status:** **PASSED**
- **Evidence:** `tests/smoke_test_core.py::test_multicast_group_delivery` — PASSED

### TC-04 — Leave-then-immediate-send timing (non-deterministic)
- **Level/category:** Boundary/timing edge case — **non-trivial, genuinely FAILED**
- **Test basis:** COND-04 / SRS 3.2.2.6 ("agentMom shall not allow receiving multicast message from a group after leaving that multicast group")
- **Preconditions:** Agent is a member of a group
- **Test data:** call `leave_group()`, then immediately send a message to that same group
- **Steps:** member.leave_group(addr, port) → sender.send("multicast", ...) with near-zero delay → poll member's events
- **Expected result:** message is NOT received (per 3.2.2.6, receipt after leaving is disallowed)
- **Actual result:** Reproduced and documented in `KNOWN_LIMITATIONS.md` item 1: a member that called `leave_group()` and received the return still received a message sent immediately after, in a standalone test during Phase 3 of development. A 5-trial rerun performed for this test case (`tests/part3b_extra_tests.py::test_leave_then_immediate_send_timing`) did not reproduce the failure (0/5), which is consistent with a timing/race condition rather than a deterministic one-direction bug.
- **Status:** **FAILED** — a documented, reproducible violation of 3.2.2.6 exists (Phase 3 finding); the condition is timing-dependent, so a clean rerun does not indicate it is fixed.
- **Evidence:** `KNOWN_LIMITATIONS.md` item 1; `tests/part3b_extra_tests.py::test_leave_then_immediate_send_timing`

### TC-05 — TTL boundary: minimum valid value (1)
- **Level/category:** Boundary
- **Test basis:** COND-05 / SRS 3.2.2.7
- **Preconditions:** N2 joined the group
- **Test data:** TTL = 1
- **Steps:** N1.send("multicast", ..., ttl=1)
- **Expected result:** accepted, delivered
- **Actual result:** delivered normally
- **Status:** **PASSED**
- **Evidence:** `tests/part3b_extra_tests.py::test_ttl_min_valid_1` — PASSED

### TC-06 — TTL boundary: maximum valid value (255)
- **Level/category:** Boundary
- **Test basis:** COND-06 / OS-level ceiling for `IP_MULTICAST_TTL` (1-byte field)
- **Test data:** TTL = 255
- **Steps:** N1.send("multicast", ..., ttl=255)
- **Expected result:** accepted, delivered
- **Actual result:** delivered normally
- **Status:** **PASSED**
- **Evidence:** `tests/part3b_extra_tests.py::test_ttl_max_valid_255` — PASSED

### TC-07 — TTL outside valid range is not rejected gracefully
- **Level/category:** Invalid/error — **non-trivial, genuinely FAILED**
- **Test basis:** COND-07 / `KNOWN_LIMITATIONS.md` item 2 ("TTL=999 ... was not pre-validated by the app")
- **Test data:** TTL = 999 (too high); TTL = -1 (negative)
- **Steps:** N1.send("multicast", ..., ttl=999); separately, ttl=-1
- **Expected result:** the app validates TTL client-side and shows a clear, graceful error (e.g. "TTL must be 1–255") without crashing
- **Actual result:** TTL=999 → unhandled `OSError: [Errno 22] Invalid argument` raised straight out of `setsockopt()` — no graceful message, this would crash the GUI event loop if uncaught there. TTL=-1 → **worse** — no error at all, `setsockopt()` silently accepts it and the message is delivered normally, i.e. an invalid input is treated as valid.
- **Status:** **FAILED**
- **Evidence:** `tests/part3b_extra_tests.py::test_ttl_out_of_range_256_raises_unhandled_error` (confirms the TTL=999 crash); `tests/part3b_extra_tests.py::test_ttl_negative_silently_accepted_and_delivered` (confirms TTL=-1 raises no exception and the message is still delivered)

### TC-08 — Non-multicast address accepted without validation
- **Level/category:** Invalid/error — **non-trivial, genuinely FAILED**
- **Test basis:** COND-08 / `KNOWN_LIMITATIONS.md` item 2 ("no multicast-address-range check exists")
- **Test data:** `"10.0.0.5:7999"` (a private unicast-range address, not in 224.0.0.0/4)
- **Steps:** N1.send("multicast", "10.0.0.5:7999", "should-be-rejected", ttl=1)
- **Expected result:** app rejects this before attempting to send, since it isn't a valid multicast address
- **Actual result:** no validation error; the send call completes without exception
- **Status:** **FAILED**
- **Evidence:** `tests/part3b_extra_tests.py::test_non_multicast_address_not_rejected` — PASSED (i.e. the absence-of-rejection was confirmed, which is itself the defect)

### TC-09 — Multi-group simultaneous receive
- **Level/category:** Normal
- **Test basis:** COND-09 / SRS 3.2.2.9
- **Test data:** agent joins two groups (`239.9.9.40:7991`, `239.9.9.41:7992`), each sent one distinct message
- **Steps:** join both groups → send to each → poll events
- **Expected result:** both messages received, correctly attributed
- **Actual result:** both `from-group-A` and `from-group-B` received correctly
- **Status:** **PASSED**
- **Evidence:** `tests/part3b_extra_tests.py::test_multi_group_simultaneous_receive` — PASSED

### TC-10 — Broadcast delivery to all agents
- **Level/category:** Normal
- **Test basis:** COND-10 / SRS 3.2.3.1/3.2.3.2
- **Test data:** payload `"broadcast hi"`, 3 agents (N1 sender, N2/N3 receivers)
- **Steps:** N1.send("broadcast", "", "broadcast hi") → poll N2, N3
- **Expected result:** both N2 and N3 receive it
- **Actual result:** both received it
- **Status:** **PASSED**
- **Evidence:** `tests/smoke_test_core.py::test_broadcast_delivery` — PASSED

### TC-11 — Encrypted unicast auto-decrypts
- **Level/category:** Normal
- **Test basis:** COND-11 / SRS 3.2.4.4 ("agentMom shall automatically decrypt encrypted message")
- **Test data:** payload `"secret payload"`, encrypt=True
- **Steps:** N1.send("unicast", ..., "secret payload", encrypt=True) → poll N2
- **Expected result:** N2's log shows both a `received` and a `decrypted` event, with the correct plaintext
- **Actual result:** exactly as expected
- **Status:** **PASSED**
- **Evidence:** `tests/smoke_test_core.py::test_encrypted_unicast_auto_decrypts` — PASSED

### TC-12 — Undecryptable message (wrong key) handled gracefully
- **Level/category:** Invalid/error
- **Test basis:** COND-12 / NFR-Security §2.4.2
- **Preconditions:** recipient's `CryptoService` uses a different key than the message was encrypted with (simulates tampering/wrong key)
- **Test data:** ciphertext encrypted under key A, delivered to an agent holding key B
- **Steps:** inject the crafted message into the recipient's inbound queue → poll events
- **Expected result:** decrypt failure is caught and surfaced as an `error` Event; the app does not crash
- **Actual result:** exactly as expected — `received` event followed by `error: decrypt failed for message from N1`
- **Status:** **PASSED**
- **Evidence:** `tests/part3b_extra_tests.py::test_undecryptable_message_handled_gracefully` — PASSED

### TC-13 — (System-level, manual) End-to-end multicast via the GUI
- **Level/category:** System-level, manual execution required
- **Test basis:** COND-13 / R2 + R3
- **Preconditions:** `python main.py` running, 3 agent windows open
- **Test data:** any group address/port entered into two windows' Group panels; any message text
- **Steps:** 1) In Window A and Window B, enter the same multicast address/port and click Join. 2) In Window A, select "multicast", enter the message, click Send. 3) Observe Window B's log panel.
- **Expected result:** Window B's log panel shows the received message
- **Actual result:** Confirmed — the recipient window's log panel showed a RECV line for the message sent from the sender window after both joined the same group address/port. Note: the first send attempt used a mistyped address (one extra octet, `239.1.1.1.1:5000`) and failed with `getaddrinfo failed`; the address was corrected and the retried send succeeded as described. This is a user input error during manual execution, not an application defect — `230.x`/`239.x`-style addresses are otherwise handled correctly (see TC-09).
- **Status:** **PASSED**
- **Evidence:** Manually executed by the team on Windows 10 with Python 3.x; screenshot in `docs/evidence/part3b_tc13_multicast.png` (includes the initial mistyped-address error and the corrected retry).

### TC-14 — (System-level, manual) Conversation-architecture switch changes visible behaviour
- **Level/category:** System-level, manual execution required
- **Test basis:** COND-14 / R6 (3.2.5.1/3.2.5.2)
- **Preconditions:** app running
- **Test data:** set one agent's conversation mode to agent-controlled, another to component-controlled
- **Steps:** 1) Send a unicast message to the agent-controlled agent. 2) Observe whether it auto-sends an ACK back without you clicking anything. 3) Repeat, sending to the component-controlled agent instead — it should NOT auto-reply.
- **Expected result:** only the agent-controlled agent auto-acks
- **Actual result:** Confirmed — the window set to agent-controlled automatically sent an ACK back with no manual Send click; the window left as component-controlled did not auto-reply under the same conditions.
- **Status:** **PASSED**
- **Evidence:** Manually executed by the team; screenshot attached separately in `docs/evidence/`.

### TC-15 — (System-level, manual) Mode selector correctly routes all three modes
- **Level/category:** System-level, manual execution required
- **Test basis:** COND-15 / R7 (§2.2.4)
- **Preconditions:** app running, 3 windows
- **Test data:** one message per mode
- **Steps:** From one window's Send panel, send one message each as unicast (to a specific window), multicast (to a group two windows joined), and broadcast. Observe all windows' log panels after each send.
- **Expected result:** unicast reaches only the targeted window; multicast reaches only group members; broadcast reaches all
- **Actual result:** Confirmed — unicast arrived only at the targeted window, multicast arrived only at group members, and broadcast arrived at both other windows. During execution, sending with a blank Target field (before it was filled in) produced three `ERROR: send failed for [...] -> : invalid literal for int() with base 10: ''` lines rather than a graceful validation message — an additional, previously undocumented input-validation gap distinct from TC-07/TC-08 (empty target vs. invalid TTL/address), observed directly in the evidence screenshot.
- **Status:** **PASSED** (the routing behaviour itself matched expectations; the blank-target crash is recorded as a separate observation, not a failure of this test's stated objective)
- **Evidence:** Manually executed by the team; screenshot in `docs/evidence/part3b_tc15_mode_routing.png` (includes the blank-target error lines on A2)

---

## Table C — Traceability Record

| Requirement | Condition | Test case | Execution result | Defect report |
|---|---|---|---|---|
| R1 | COND-01 | TC-01 | PASSED | N/A |
| R1 / NFR-Reliability | COND-02 | TC-02 | PASSED | N/A |
| R2 | COND-03 | TC-03 | PASSED | N/A |
| R2 | COND-04 | TC-04 | FAILED | BUG-01 (multicast leave/join timing) |
| R3 | COND-05 | TC-05 | PASSED | N/A |
| R3 | COND-06 | TC-06 | PASSED | N/A |
| R3 | COND-07 | TC-07 | FAILED | BUG-02 (TTL validation missing/crashes) |
| R3 | COND-08 | TC-08 | FAILED | BUG-03 (multicast address validation missing) |
| R3 | COND-09 | TC-09 | PASSED | N/A |
| R4 | COND-10 | TC-10 | PASSED | N/A |
| R5 | COND-11 | TC-11 | PASSED | N/A |
| R5 / NFR-Security | COND-12 | TC-12 | PASSED | N/A |
| R2 + R3 | COND-13 | TC-13 | PASSED | N/A |
| R6 | COND-14 | TC-14 | PASSED | N/A |
| R7 | COND-15 | TC-15 | PASSED | BUG-04 (blank Target field crash, observed as a side effect during this test) |

**Category coverage check:**
- Boundary cases (≥2 required): TC-05, TC-06 ✓ (TC-04 is also a timing-boundary case)
- Invalid/error cases (≥2 required): TC-02, TC-07, TC-08, TC-12 ✓
- Manual system-level cases (≥3 required): TC-13, TC-14, TC-15 ✓ — all executed by hand on the actual GUI, all PASSED
- Genuine FAILED/BLOCKED, non-trivial (≥2 required): TC-04, TC-07, TC-08 ✓ (3 supplied)

## Summary

15 test cases were executed in total: 12 at the `agent_core` layer (automated) and 3 at the GUI layer (manual, system-level). 12 cases PASSED and 3 cases genuinely FAILED (TC-04, TC-07, TC-08), each tied to a documented gap in `KNOWN_LIMITATIONS.md`. The 3 FAILED cases are carried forward as defect candidates in Part 4.

One additional defect was observed as a side effect during TC-15's manual execution rather than through a dedicated test case: sending with a blank Target field raises an unhandled `ValueError` (`invalid literal for int() with base 10: ''`) instead of a graceful validation message. This is a genuine, reproducible gap distinct from the TTL/address validation gaps in TC-07/TC-08, and is also a candidate for the Part 4 defect log.
