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

- [ ] `CryptoService(key)`: AES-GCM `encrypt(plaintext) -> b64`, `decrypt(b64) -> plaintext`.
- [ ] Key generated once at process start (`main.py`), passed to every `AgentNode` in-process (stands in for the SRS's key-distribution agent).

**Done when:** a standalone round-trip test encrypts and decrypts a string correctly, and decrypting with a different key raises rather than silently returning garbage. Covers 3.2.4.1–3.2.4.6.

---

## Phase 6 — Conversation controller (`agent_core/conversation.py`)

- [ ] `ConversationController` ABC with `on_message_received` / `decide_next_action`.
- [ ] `AgentControlledConversation` — autonomous logic (e.g. auto-ack on receive).
- [ ] `ComponentControlledConversation` — no autonomous behavior; every action requires an explicit external call.

**Done when:** a standalone test wires each implementation to a fake `AgentNode` and confirms the agent-controlled one reacts to a received message on its own, while the component-controlled one does nothing until externally driven. Covers 3.2.5.1/3.2.5.2.

---

## Phase 7 — `AgentNode` + `MessageRouter` (integration)

- [ ] `AgentNode(agent_id, unicast_port, crypto_service, conversation_controller)` owns one instance of each transport + a single outbound event `queue.Queue`.
- [ ] `router.py`: `send(mode, target, payload, **opts)` dispatches to the right transport based on `mode`.
- [ ] `AgentNode.poll_events()` — non-blocking drain of the event queue (for the GUI to call later).

**Done when:** a standalone script creates 2–3 `AgentNode`s (no GUI) and exercises unicast + multicast + broadcast + encrypted send, all through the single `AgentNode` API, confirming the core layer is complete and GUI-independent. Covers §2.2.4.

---

## Phase 8 — Core layer test pass (pre-GUI checkpoint)

- [ ] Write a short `tests/smoke_test_core.py` exercising Phases 2–7 end-to-end without any GUI.
- [ ] Fix anything broken before touching `agent_gui/` — the core layer should be solid on its own first.

**Done when:** the smoke test runs clean. This is the natural checkpoint to pause and review before starting GUI work.

---

## Phase 9 — `AgentWindow` skeleton (`agent_gui/agent_window.py`)

- [ ] `AgentWindow(Toplevel, agent_node)` — window title = agent ID, layout placeholders for the three panels.
- [ ] `root.after(100, self._poll)` loop draining `agent_node.poll_events()` — wire this early since it's the thread-safety-critical piece (architecture.md §7).

**Done when:** opening the window and manually pushing a fake event onto the queue shows it appear in a (temporary) label/log within ~100ms.

---

## Phase 10 — Log panel (`agent_gui/log_panel.py`)

- [ ] Read-only, auto-scrolling `Text` widget; `append(event)` prefixes a timestamp and, where relevant, the active conversation-control mode tag.

**Done when:** every event type (sent, received, joined, left, encrypted, decrypted, error) has a distinct, readable log line format.

---

## Phase 11 — Send panel (`agent_gui/send_panel.py`)

- [ ] Mode selector (unicast/multicast/broadcast), target/group+port fields, TTL field (enabled only for multicast), encrypt checkbox, Send button.
- [ ] Send button calls `agent_node` via `router.send(...)` — never touches sockets directly.

**Done when:** manually sending a unicast message between two open agent windows shows up correctly in both logs.

---

## Phase 12 — Group panel (`agent_gui/group_panel.py`)

- [ ] Group address/port entry, Join / Leave buttons, live list of currently joined groups (reflects `agent_node`'s actual joined-group state, not just UI state).

**Done when:** joining/leaving in the GUI visibly changes what a multicast send from another window does/doesn't deliver.

---

## Phase 13 — Multi-window launcher (`main.py`, final form)

- [ ] Generates the shared AES key once.
- [ ] Spawns N `AgentWindow`s (default 3), each with a unique unicast port, sharing the crypto key.
- [ ] Per-window dropdown to select agent-controlled vs component-controlled conversation mode (architecture.md §4.6).

**Done when:** `python main.py` opens 3 fully wired agent windows.

---

## Phase 14 — End-to-end manual verification

Run through every FR from Part 1 manually across the 3 open windows before calling Part 2 done:

- [ ] Unicast send/receive between two specific agents (message doesn't appear at the third).
- [ ] Join a multicast group on 2 of 3 agents, send, confirm only joined agents receive; leave and confirm messages stop arriving.
- [ ] Multicast TTL field takes effect (no crash on TTL=0 or an out-of-range value — record actual behavior).
- [ ] Broadcast reaches all agents on the same machine.
- [ ] Encrypted unicast/multicast: checkbox toggles encryption; receiver auto-decrypts and displays correct plaintext.
- [ ] Switch one agent to component-controlled mode and confirm it does NOT auto-react to an incoming message the way an agent-controlled one does.
- [ ] Deliberately trigger a failure (e.g. send to a closed port) and confirm it's logged, not silently dropped.

**Done when:** all of the above are observed and behave as documented in `architecture.md` §10 — including the deliberately-unfixed `(c)` assumptions, which should misbehave in the *expected* way, not crash the app.

---

## Phase 15 — Handoff to Part 3

- [ ] Note in a short `KNOWN_LIMITATIONS.md` (or an appendix here) any behavior observed in Phase 14 that differs from what was predicted in Part 1 — this becomes direct input for Part 3's functional test derivation and Part 4's defect log.
- [ ] Confirm `agent_core/` has no `tkinter` imports (quick grep) — keeps it eligible for isolated unit testing in Part 3.

**Done when:** Part 2 is feature-complete, manually verified, and hands off a clean seam for Part 3's SonarQube run and test derivation.
