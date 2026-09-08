# Part 2 — Implementation Plan

Companion to `architecture.md`. Ordered so the network/business logic (`agent_core/`) is built and smoke-tested **before** any GUI code exists — each phase produces something independently verifiable.

Legend: [ ] not started · [x] done

---

## Phase 0 — Project setup

- [x] Create `part2_gui_baseline/` with the folder layout from `architecture.md` §2 (`agent_core/`, `agent_gui/`, `tests/`, empty `__init__.py` files).
- [x] Create a virtual environment; add `requirements.txt` with `cryptography` (tkinter/socket/threading/struct/queue are all stdlib, no install needed).
- [x] `main.py` stub that just opens an empty Tk root, to confirm Tkinter works in the environment. (Required installing the system `python3-tk` package — not pip-installable — before the venv could import it.)

**Done when:** `python main.py` opens a blank window with no errors. ✅ Verified.

---

## Phase 1 — Message format (`agent_core/message.py`)

- [x] `Message` dataclass: `type, sender_id, sender_addr, timestamp, encrypted, payload`.
- [x] `to_bytes()` / `from_bytes()` — JSON (de)serialization per the wire schema in `architecture.md` §5.
- [x] Length-prefix helpers for TCP framing (`pack_frame(bytes) -> bytes`, `read_frame(sock) -> bytes`).

**Done when:** a standalone script can round-trip a `Message` through `to_bytes`/`from_bytes` and get an identical object back. ✅ Verified — also round-tripped `pack_frame`/`read_frame` over a real TCP socket.

---

## Phase 2 — Unicast transport (`agent_core/unicast.py`)

- [x] `UnicastTransport(agent_id, port)`: TCP listener thread (`accept()` loop), per-connection handler thread reading one length-prefixed frame.
- [x] `send(target_addr, target_port, message)`: opens connection, writes one framed message, closes.
- [x] Inbound messages pushed to a `queue.Queue` passed in from `AgentNode`.

**Done when:** two standalone Python processes (no GUI) on different ports can unicast a message to each other and it's received intact — this is the first real, non-mocked network test. Covers 3.2.1.1–3.2.1.4. ✅ Verified with two OS processes (ports 6101/6102).

---

## Phase 3 — Multicast transport (`agent_core/multicast.py`)

- [x] `join_group(addr, port)` — `IP_ADD_MEMBERSHIP`, starts a per-group recv thread.
- [x] `leave_group(addr, port)` — `IP_DROP_MEMBERSHIP`, stops the thread.
- [x] `send(addr, port, message, ttl=1)` — `IP_MULTICAST_TTL` set per-send.
- [x] Support multiple simultaneously-joined groups (one thread each, shared queue).

**Done when:** 3 standalone processes join the same group, one sends, the other two receive it — and a message sent after `leave_group()` is confirmed NOT to arrive (this is the exact (c)-flagged timing assumption from Part 1 — test it here first, informally, before Part 3 formalizes it). Covers 3.2.2.1–3.2.2.9. ✅ Verified with 3 OS processes (group 239.1.1.1:6300) — both standing receivers got both messages; the receiver that called `leave_group()` mid-test **still received** the message sent after leave returned, confirming the (c)-flagged async leave timing — recorded here for Part 3, not treated as a bug.

---

## Phase 4 — Broadcast transport (`agent_core/broadcast.py`)

- [x] UDP socket with `SO_BROADCAST`, `send(payload)` to the subnet broadcast address, recv loop thread.
- [x] No permission pre-check (per architecture — let it fail naturally and log the error if it does).

**Done when:** 2+ standalone processes on the same machine send/receive a broadcast message. Covers 3.2.3.1–3.3.3.3. ✅ Verified with 3 OS processes (port 6400) — one sender, two receivers, both received the broadcast intact. No permission error surfaced in this environment; the uncaught-`OSError`/`PermissionError` path (architecture.md §4.4) remains untested here and is a Part 3 candidate on stricter environments.

---

## Phase 5 — Crypto service (`agent_core/crypto_service.py`)

- [x] `CryptoService(key)`: AES-GCM `encrypt(plaintext) -> b64`, `decrypt(b64) -> plaintext`.
- [x] Key generated once at process start (`main.py`), passed to every `AgentNode` in-process (stands in for the SRS's key-distribution agent).

**Done when:** a standalone round-trip test encrypts and decrypts a string correctly, and decrypting with a different key raises rather than silently returning garbage. Covers 3.2.4.1–3.2.4.6. ✅ Verified — round-trip correct; wrong-key decrypt raised `cryptography.exceptions.InvalidTag`.

---

## Phase 6 — Conversation controller (`agent_core/conversation.py`)

- [x] `ConversationController` ABC with `on_message_received` / `decide_next_action`.
- [x] `AgentControlledConversation` — autonomous logic (e.g. auto-ack on receive).
- [x] `ComponentControlledConversation` — no autonomous behavior; every action requires an explicit external call.

**Done when:** a standalone test wires each implementation to a fake `AgentNode` and confirms the agent-controlled one reacts to a received message on its own, while the component-controlled one does nothing until externally driven. Covers 3.2.5.1/3.2.5.2. ✅ Verified.

---

## Phase 7 — `AgentNode` + `MessageRouter` (integration)

- [x] `AgentNode(agent_id, unicast_port, crypto_service, conversation_controller)` owns one instance of each transport + a single outbound event `queue.Queue`.
- [x] `router.py`: `send(mode, target, payload, **opts)` dispatches to the right transport based on `mode`.
- [x] `AgentNode.poll_events()` — non-blocking drain of the event queue (for the GUI to call later).

**Done when:** a standalone script creates 2–3 `AgentNode`s (no GUI) and exercises unicast + multicast + broadcast + encrypted send, all through the single `AgentNode` API, confirming the core layer is complete and GUI-independent. Covers §2.2.4. ✅ Verified with 3 in-process `AgentNode`s (N1 agent-controlled, N2/N3 component-controlled) — unicast, multicast, broadcast, and encrypted unicast (with auto-decrypt) all passed; agent-controlled auto-ack fired with no external drive, component-controlled did not.

---

## Phase 8 — Core layer test pass (pre-GUI checkpoint)

- [x] Write a short `tests/smoke_test_core.py` exercising Phases 2–7 end-to-end without any GUI.
- [x] Fix anything broken before touching `agent_gui/` — the core layer should be solid on its own first.

**Done when:** the smoke test runs clean. This is the natural checkpoint to pause and review before starting GUI work. ✅ Verified — `pytest tests/smoke_test_core.py` (5 tests) passes clean.

**Bug found and fixed here (not a Part 1 (c)-flagged AI assumption — a genuine lifecycle bug):** `UnicastTransport`, `MulticastTransport`, and `BroadcastTransport` all blocked their recv/accept loops on the raw socket call with no timeout, relying on another thread's `close()` to unblock them — on Linux this is not reliable, so `stop()`/`leave_group()` could return while the listener thread was still alive and the port still bound, breaking teardown/rebinding (surfaced as repeated `AgentNode` creation failing with "Address already in use"). Fixed by giving each listening/recv socket a 0.5s `settimeout()` so the loop polls its stop flag instead of blocking indefinitely.

---

## Phase 9 — `AgentWindow` skeleton (`agent_gui/agent_window.py`)

- [x] `AgentWindow(Toplevel, agent_node)` — window title = agent ID, layout placeholders for the three panels.
- [x] `root.after(100, self._poll)` loop draining `agent_node.poll_events()` — wire this early since it's the thread-safety-critical piece (architecture.md §7).

**Done when:** opening the window and manually pushing a fake event onto the queue shows it appear in a (temporary) label/log within ~100ms. ✅ Verified against a real Tk display (`DISPLAY=:0` available in this environment) — pushed an `Event` directly onto `agent_node.events` and confirmed the placeholder label updated via the `root.after` poll loop.

---

## Phase 10 — Log panel (`agent_gui/log_panel.py`)

- [x] Read-only, auto-scrolling `Text` widget; `append(event)` prefixes a timestamp and, where relevant, the active conversation-control mode tag.

**Done when:** every event type (sent, received, joined, left, encrypted, decrypted, error) has a distinct, readable log line format. ✅ Verified — all 7 kinds render as distinct, color-tagged, timestamped lines; wired into `AgentWindow` in place of the Phase 9 placeholder and confirmed a real event flows through the poll loop into the log `Text` widget.

---

## Phase 11 — Send panel (`agent_gui/send_panel.py`)

- [x] Mode selector (unicast/multicast/broadcast), target/group+port fields, TTL field (enabled only for multicast), encrypt checkbox, Send button.
- [x] Send button calls `agent_node` via `router.send(...)` — never touches sockets directly.

**Done when:** manually sending a unicast message between two open agent windows shows up correctly in both logs. ✅ Verified — drove the real `SendPanel` widgets on one `AgentWindow` and confirmed a `SENT` line appeared in its own log and a matching `RECV` line appeared in the second window's log.

---

## Phase 12 — Group panel (`agent_gui/group_panel.py`)

- [x] Group address/port entry, Join / Leave buttons, live list of currently joined groups (reflects `agent_node`'s actual joined-group state, not just UI state).

**Done when:** joining/leaving in the GUI visibly changes what a multicast send from another window does/doesn't deliver. ✅ Verified with 3 windows — after joining via the real Join button, only the joined window's log showed the multicast; a window that never joined didn't get it; Leave correctly cleared the joined-groups list, reading straight from `agent_node.multicast.groups` each time.

---

## Phase 13 — Multi-window launcher (`main.py`, final form)

- [x] Generates the shared AES key once.
- [x] Spawns N `AgentWindow`s (default 3), each with a unique unicast port, sharing the crypto key.
- [x] Per-window dropdown to select agent-controlled vs component-controlled conversation mode (architecture.md §4.6).

**Done when:** `python main.py` opens 3 fully wired agent windows. ✅ Verified — ran `python main.py` as a real subprocess and confirmed via `ss` that it bound TCP 6001/6002/6003 (the 3 agents' unicast ports) and 3 UDP sockets on the shared broadcast port 6400; separately confirmed via `build_agents`/`build_windows` that all 3 windows have unique ports, one shared `CryptoService`, all 3 panels present, and that the conversation-mode dropdown actually swaps the live `ConversationController` instance on the agent.

---

## Phase 14 — End-to-end manual verification

Run through every FR from Part 1 manually across the 3 open windows before calling Part 2 done:

- [x] Unicast send/receive between two specific agents (message doesn't appear at the third).
- [x] Join a multicast group on 2 of 3 agents, send, confirm only joined agents receive; leave and confirm messages stop arriving.
- [x] Multicast TTL field takes effect (no crash on TTL=0 or an out-of-range value — record actual behavior).
- [x] Broadcast reaches all agents on the same machine.
- [x] Encrypted unicast/multicast: checkbox toggles encryption; receiver auto-decrypts and displays correct plaintext.
- [x] Switch one agent to component-controlled mode and confirm it does NOT auto-react to an incoming message the way an agent-controlled one does.
- [x] Deliberately trigger a failure (e.g. send to a closed port) and confirm it's logged, not silently dropped.

**Done when:** all of the above are observed and behave as documented in `architecture.md` §10 — including the deliberately-unfixed `(c)` assumptions, which should misbehave in the *expected* way, not crash the app.

✅ **Verified — this environment has a real X display (`DISPLAY=:0`), so verification drove the real `AgentWindow`/`SendPanel`/`GroupPanel` widgets on 3 live windows (real sockets/threads, not literal human mouse clicks) rather than being a claim I couldn't back up. Results:**

1. **Unicast targeted delivery** — A1→A2 unicast arrived at A2's log; A3's log had no `RECV` for it.
2. **Multicast group delivery** — A1 and A2 joined `239.7.7.7:6900`; a send from A3 (not joined) reached A1/A2 only. Leave cleared the Group panel's list correctly (reads real `agent_node.multicast.groups` state). A message sent shortly after leaving was **not** received in this run — consistent with, but not a guarantee against, the `(c)`-flagged async leave timing already documented in Phase 3.
3. **Multicast TTL edge cases** — `TTL=0`: no crash, message did not arrive (locally-scoped TTL). `TTL=999` (outside the valid 0–255 byte range for `IP_MULTICAST_TTL`): raised `OSError: [Errno 22] Invalid argument` from the OS — surfaced as an `ERROR` log line via the Phase-14 fix below, app kept running. No stricter validation was added (per the Part 1 (c) assumption on loose TTL validation) — this is the actual OS-level failure mode, recorded rather than pre-validated away.
4. **Broadcast reach** — A1's broadcast arrived in both A2's and A3's logs.
5. **Encrypted unicast** — encrypt checkbox produced an `ENCRYPTED` line on send and a `DECRYPTED` line with correct plaintext on receipt; ciphertext never appeared in the receiver's `RECV` line.
6. **Conversation-mode switch** — switching A2 to agent-controlled via the dropdown made it auto-ACK an incoming unicast with zero external drive; A3, left component-controlled, did not.
7. **Deliberate failure (closed port)** — unicast to a port nothing was listening on raised `ConnectionRefusedError` and produced an `ERROR` log line (`send failed for [unicast] -> 127.0.0.1:6799: [Errno 111] Connection refused`) — not silently dropped.

**Fix made during this phase (matches architecture.md §10's explicit "delivery failures logged, not retried or acknowledged," not a regression of a deliberately-left defect):** `AgentNode.send()` had no path to the log panel for outbound failures at all — a failed `router.send()` would only ever surface as an unhandled exception. Wrapped it to push an `error` Event before re-raising, so failures are both visible in-app and still not silently swallowed.

---

## Phase 15 — Handoff to Part 3

- [x] Note in a short `KNOWN_LIMITATIONS.md` (or an appendix here) any behavior observed in Phase 14 that differs from what was predicted in Part 1 — this becomes direct input for Part 3's functional test derivation and Part 4's defect log.
- [x] Confirm `agent_core/` has no `tkinter` imports (quick grep) — keeps it eligible for isolated unit testing in Part 3.

**Done when:** Part 2 is feature-complete, manually verified, and hands off a clean seam for Part 3's SonarQube run and test derivation. ✅ Verified — `KNOWN_LIMITATIONS.md` written at the repo root, mapping all 7 Part 1 `(c)` assumptions to what was actually observed, plus a separate note on the 2 real implementation bugs found and fixed along the way (listener-thread shutdown, and unlogged send failures). `grep -rn tkinter agent_core/` returns nothing — confirmed clean.

---

## Part 2 status: feature-complete

All 15 phases done and verified (Phases 1–4, 9 verified with real OS-process/network tests earlier in this doc's history; Phases 5–15 verified in this pass, including a full Phase 14 run driving 3 real `AgentWindow`s on this environment's real X display). See `KNOWN_LIMITATIONS.md` for what to carry into Part 3.
