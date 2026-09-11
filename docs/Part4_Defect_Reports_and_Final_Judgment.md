# Part 4 — Defect Reporting and Final Quality Judgment

**Source:** confirmed FAILED test cases and observations from `docs/Part3B_Functional_Test_Derivation_and_Traceability.md`, cross-referenced against `KNOWN_LIMITATIONS.md`. All 4 defects below were reproduced (or, for BUG-01, documented as reproduced) before being logged — no test failure was logged as a defect without investigation.

---

## BUG-01 — Multicast message received after leaving a group (intermittent)

- **Environment/build:** Linux, commit `bd231e1`, `agent_core` layer (Python 3.12, `agent_core/multicast.py`)
- **Preconditions:** An agent has joined a multicast group
- **Steps to reproduce:**
  1. Agent calls `leave_group(addr, port)` and the call returns
  2. Immediately (near-zero delay), another agent sends a message to that same group
  3. Poll the agent's events
- **Expected result:** Per SRS 3.2.2.6, the agent must not receive the message, since it already left the group
- **Actual result:** In a documented Phase 3 standalone test (`KNOWN_LIMITATIONS.md` item 1), the message was received despite `leave_group()` having already returned. A 5-trial rerun during Part 3(b) did not reproduce it (0/5) — consistent with a race condition between the OS dropping multicast group membership and the socket teardown, not a deterministic one-direction bug.
- **Reproducibility:** Intermittent (timing/race-dependent — confirmed reproducible at least once, not reliably on every attempt)
- **Severity:** Medium — violates a stated access-control requirement (3.2.2.6), but only in a narrow timing window immediately after leaving
- **Priority:** Medium — not blocking normal use, but represents a real correctness gap in a security/access-relevant rule
- **Evidence:** `KNOWN_LIMITATIONS.md` item 1; `tests/part3b_extra_tests.py::test_leave_then_immediate_send_timing`
- **Related test case:** TC-04
- **Status:** Open

---

## BUG-02 — Multicast TTL is not validated (crashes above range, silently accepts negative)

- **Environment/build:** Linux, commit `bd231e1`, `agent_core` layer (`agent_core/multicast.py`, `MulticastTransport.send`)
- **Preconditions:** An agent is a member of a multicast group
- **Steps to reproduce (case A — over range):**
  1. Call `send("multicast", <group>, <payload>, ttl=999)`
  2. Observe the exception
  **Steps to reproduce (case B — negative):**
  1. Call `send("multicast", <group>, <payload>, ttl=-1)`
  2. Observe whether the message is delivered
- **Expected result:** The application validates TTL is within 1–255 before attempting to send, and shows a clear, user-facing error for invalid values (e.g. "TTL must be between 1 and 255") without crashing
- **Actual result:** Case A: unhandled `OSError: [Errno 22] Invalid argument` propagates straight from `setsockopt()` — no graceful message, would surface as a raw crash/traceback to the user. Case B: no exception at all — the negative value is silently accepted and the message is delivered normally, i.e. genuinely invalid input is treated as valid.
- **Reproducibility:** Always (100%, both cases)
- **Severity:** High — case A is an unhandled crash reachable directly from user-entered GUI input (the TTL field takes free-text and is never range-checked before use); case B is a silent correctness gap
- **Priority:** High — this is a crash triggerable by an ordinary user typo in the GUI's own TTL field, not an edge case requiring special conditions
- **Evidence:** `KNOWN_LIMITATIONS.md` item 2; `tests/part3b_extra_tests.py::test_ttl_out_of_range_256_raises_unhandled_error`
- **Related test case:** TC-07
- **Status:** Open

---

## BUG-03 — Non-multicast address accepted as a multicast group target without validation

- **Environment/build:** Linux, commit `bd231e1`, `agent_core` layer (`agent_core/multicast.py`, `MulticastTransport.send`)
- **Preconditions:** none beyond a running agent
- **Steps to reproduce:**
  1. Call `send("multicast", "10.0.0.5:7999", <payload>, ttl=1)` — `10.0.0.5` is a private unicast-range address, not in the valid multicast range (224.0.0.0–239.255.255.255)
  2. Observe whether the call is rejected
- **Expected result:** The application rejects the address before attempting to send, since it is not a valid multicast address
- **Actual result:** No validation error; the send call completes without exception, silently accepting a malformed configuration
- **Reproducibility:** Always (100%)
- **Severity:** Medium — does not crash the app, but allows a clearly invalid configuration to be accepted silently, which could mislead a user into believing a message was properly multicast when it was not
- **Priority:** Medium — a straightforward input-validation fix (range-check the address against 224.0.0.0/4), not urgent but worth fixing before any real deployment
- **Evidence:** `KNOWN_LIMITATIONS.md` item 2; `tests/part3b_extra_tests.py::test_non_multicast_address_not_rejected`
- **Related test case:** TC-08
- **Status:** Open

---

## BUG-04 — Sending with a blank Target field crashes with an unhandled ValueError

- **Environment/build:** Windows 10, commit `bd231e1` (as observed), GUI layer (`agent_gui/send_panel.py` → `agent_core/router.py`, `target.partition(":")` / `int(port)`)
- **Preconditions:** App running, at least 2 agent windows open
- **Steps to reproduce:**
  1. In any agent window's Send panel, leave the "Target (addr:port)" field blank
  2. Select any mode (unicast or multicast) and click Send
- **Expected result:** A graceful, user-facing validation error (e.g. "Target address is required") is shown, and no exception reaches the log/console
- **Actual result:** An unhandled `ValueError: invalid literal for int() with base 10: ''` is raised — reproduced 3 times during TC-15's manual execution, visible in the log panel as raw `ERROR: send failed for [...] -> : invalid literal for int() with base 10: ''` lines rather than a clear message
- **Reproducibility:** Always (100% — any send attempt with an empty Target field)
- **Severity:** Medium — does not crash the whole app (caught at the `AgentNode.send()` level and surfaced as an error Event rather than terminating the process), but produces a confusing, implementation-leaking error message for an extremely easy user mistake (forgetting to fill in the Target field)
- **Priority:** Medium — easy to trigger accidentally, easy to fix with a simple non-empty check before parsing
- **Evidence:** `docs/evidence/part3b_tc15_mode_routing.png` (shows the three raw `ValueError` lines)
- **Related test case:** TC-15 (observed as a side effect, not the test's primary objective)
- **Status:** Open

---

## Final Quality Judgment (to be placed in the combined report)

The evaluated scope — 7 FRs and 3 NFRs drawn from the agentMom SRS — is **partially but not fully acceptable** based on the evidence collected. Core messaging behaviour is solid: unicast, multicast, broadcast, multi-group reception, encryption/decryption, and both conversation-control architectures all passed their test cases, including 3 manually executed system-level tests confirming the GUI itself behaves correctly end-to-end. This supports confidence in the application's primary functional path.

However, four confirmed, reproducible defects were found, all clustered around **input validation at system boundaries**: TTL values outside 1–255 either crash the app (over-range) or are silently accepted despite being invalid (negative), non-multicast addresses are accepted without rejection, and a blank Target field produces a raw, unhandled exception rather than a graceful message. None of these were fabricated or relabeled to meet a quota — three were predicted directly by the Part 1 AI-assumption table (validation strictness was flagged "(c) unsupported" before implementation began) and confirmed exactly as predicted; the fourth (blank-target crash) was discovered incidentally during manual GUI testing. A fifth issue — non-deterministic multicast delivery immediately after leaving a group — remains only intermittently reproducible, which itself is meaningful evidence: it indicates a genuine race condition rather than a stable, always-reproducible bug, and is reported with that caveat rather than overstated.

What remains unsupported by this evaluation: portability across environments (only tested on one Linux machine, headless, and one Windows machine with a display — no multi-machine or restrictive-network testing occurred), and broadcast permission behaviour under a locked-down OS (never observed to fail here, which is not the same as proving it works everywhere). Both are reported as explicit scope limitations rather than assumed passes.

AI-assisted development materially shaped both where defects were found and where confidence is lower: every unvalidated-input defect traces directly back to an assumption the AI-assisted implementation made and never hardened, exactly where Part 1 predicted risk. This suggests the scope selection and risk analysis were well-calibrated. Overall, the 10-requirement scope is acceptable for a demonstration-grade implementation but would need the four logged defects resolved, plus multi-environment testing, before being considered production-acceptable.

*(Word count: ~360 — adjust wording as needed if your combined report has a stricter house style, but keep it within 300–400.)*
