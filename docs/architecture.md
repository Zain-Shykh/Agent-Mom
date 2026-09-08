# Part 2 — Architecture Document

**Project:** agentMom GUI Baseline (Part 2 — AI-Generated GUI Baseline, 10 marks)
**Stack:** Python 3, `tkinter`/`ttk` (GUI), `socket`/`struct`/`threading` (stdlib networking), `cryptography` (AES)
**Scope:** Implements the 7 FR + 3 NFR selected in `Part1_Requirement_Scope_and_AI_Assumptions.md`.

---

## 1. Design Goals

1. **Real networking, not mocked.** Every agent window binds to a real local socket. Unicast, multicast, and broadcast are exercised as actual TCP/UDP traffic on `localhost`/`127.0.0.1`, so functional tests in Part 3 evaluate genuine behavior, not stubbed logic.
2. **Core logic is GUI-independent.** All networking, encryption, and conversation-control logic lives in a layer with zero `tkinter` imports, so it can be unit-tested directly (`pytest`) and separately from the manual/system-level GUI test cases required in Part 3.
3. **Failures are visible, never swallowed.** Per the Reliability NFR (§2.4.1), best-effort delivery is allowed — silently discarding a failure is not. Every send/receive/join/leave outcome, success or error, is written to the on-screen log.
4. **Two genuinely separate conversation-control code paths.** 3.2.5.1/3.2.5.2 require both an agent-controlled and a component-controlled architecture to exist as real, distinct implementations — not one degenerate case of the other.

---

## 2. Directory / Module Layout

```
part2_gui_baseline/
├── main.py                     # entry point: launches N agent windows in one process
│
├── agent_core/                 # pure Python — no tkinter import anywhere
│   ├── __init__.py
│   ├── agent_node.py           # AgentNode: identity, owns transports + conversation controller
│   ├── message.py              # Message dataclass + JSON wire (de)serialization
│   ├── unicast.py              # UnicastTransport (TCP)
│   ├── multicast.py            # MulticastTransport (UDP multicast, group join/leave, TTL)
│   ├── broadcast.py            # BroadcastTransport (UDP broadcast)
│   ├── crypto_service.py       # CryptoService: AES encrypt/decrypt
│   ├── conversation.py         # ConversationController strategy + two implementations
│   └── router.py               # MessageRouter: mode -> transport dispatch
│
├── agent_gui/                  # tkinter/ttk only — talks to agent_core, never touches sockets
│   ├── __init__.py
│   ├── agent_window.py         # AgentWindow(Toplevel): wires one AgentNode to its panels
│   ├── send_panel.py           # mode selector, target/group+port, TTL, encrypt checkbox
│   ├── group_panel.py          # group address entry, Join/Leave buttons, joined-groups list
│   └── log_panel.py            # scrolling, timestamped event log
│
└── tests/                      # Part 3 will populate this (pytest for agent_core, manual scripts for GUI)
```

---

## 3. Process & Window Model

Single OS process, single Tk root. The root spawns a configurable number of **Agent windows** (default 3), each owning one `AgentNode` bound to a unique unicast TCP port.

```
main.py
 └─ Tk root
     ├─ AgentWindow "A1" ── AgentNode(agent_id="A1", unicast_port=6001)
     ├─ AgentWindow "A2" ── AgentNode(agent_id="A2", unicast_port=6002)
     └─ AgentWindow "A3" ── AgentNode(agent_id="A3", unicast_port=6003)
```

Agents discover each other by address/port entered directly into the Send panel (no discovery service — out of scope of the SRS). Multicast groups are joined by entering a multicast address (e.g. `239.1.1.1`) and port shared across the agents that should be in the group.

---

## 4. Core Layer (`agent_core/`)

### 4.1 `AgentNode`

The central object per agent. Owns:
- one `UnicastTransport`
- one `MulticastTransport` (manages zero or more joined groups)
- one `BroadcastTransport`
- one `CryptoService`
- one `ConversationController` (swappable — see §4.6)
- an outbound `queue.Queue` of inbound events, consumed by the GUI

Public surface used by the GUI layer:
```python
agent.send(mode, target, payload, *, ttl=None, encrypt=False)
agent.join_group(addr, port)
agent.leave_group(addr, port)
agent.poll_events()          # non-blocking; GUI calls this via root.after()
```

### 4.2 `UnicastTransport` (3.2.1.1–3.2.1.4)

- One TCP listener thread (`accept()` loop) per agent, bound to the agent's port.
- Each inbound connection is read on its own short-lived handler thread; a length-prefixed frame (4-byte big-endian length + JSON payload, see §5) is read fully before the message is queued — this avoids TCP stream/message-boundary bugs.
- `send()` opens a new TCP connection per message, writes one framed message, closes. In-order delivery for a given sender→receiver pair is guaranteed by TCP itself (Part 1 assumption, basis (a)) — no application-level sequence numbers are added.

### 4.3 `MulticastTransport` (3.2.2.1–3.2.2.9)

- `join_group(addr, port)`: creates a UDP socket, sets `IP_ADD_MEMBERSHIP` via `setsockopt`, starts a dedicated recv-loop thread for that group, stores it in `self.groups[(addr, port)]`.
- `leave_group(addr, port)`: sets `IP_DROP_MEMBERSHIP`, stops and joins the thread, removes the group. Until this call returns, the socket is still a live member — the "immediate/synchronous" join/leave timing is an AI assumption flagged as **(c) unsupported** in Part 1 and should be probed directly in Part 3 testing (e.g., a message sent immediately after `leave_group()` returns may or may not still be received).
- `send(addr, port, payload, ttl)`: sets `IP_MULTICAST_TTL` per-send, `sendto()`s the datagram. No validation beyond "is this a syntactically valid IPv4 multicast address" is performed (default TTL = 1 if unspecified) — consistent with the Part 1 (c) assumption on config validation strictness.
- Supports receiving from multiple simultaneously-joined groups (3.2.2.9) because each group has its own socket + thread, all feeding the same shared event queue.

### 4.4 `BroadcastTransport` (3.2.3.1–3.3.3.3)

- One UDP socket with `SO_BROADCAST` enabled, sending to `<broadcast>` (`255.255.255.255`) or the subnet broadcast address, and a recv-loop thread bound to the broadcast port.
- No OS-permission check is performed before sending — this directly instantiates the Part 1 (c) assumption ("assumes unrestricted broadcast permission," contradicting §2.4.4) and is expected to surface as an `OSError`/`PermissionError` on some environments, which must be logged, not caught-and-ignored.

### 4.5 `CryptoService` (3.2.4.1–3.2.4.6)

- AES-GCM via the `cryptography` library. A single symmetric key is generated at process start and shared out-of-band across all agent windows in the demo (stands in for the SRS's conceptual "key-distribution agent," §2.5.3 — flagged in Part 1 as an AI-introduced, unsupported design choice).
- `encrypt(plaintext) -> ciphertext_b64`, `decrypt(ciphertext_b64) -> plaintext`.
- The encrypt checkbox in the Send panel is per-message, satisfying "an agent may choose whether to encrypt" (3.2.4.3); receipt-side decryption is automatic and unconditional whenever the message's `encrypted` flag is `true` (3.2.4.5).

### 4.6 `ConversationController` (3.2.5.1 / 3.2.5.2)

Strategy interface:
```python
class ConversationController(ABC):
    def on_message_received(self, msg: Message) -> None: ...
    def decide_next_action(self) -> Action | None: ...
```

Two real implementations, selectable per agent window at runtime via a dropdown in `AgentWindow`:

- **`AgentControlledConversation`** — decision logic lives inside the controller itself; e.g. on receiving a message it can autonomously decide to auto-acknowledge, entirely independent of the GUI. The agent "owns" the conversation.
- **`ComponentControlledConversation`** — the controller holds no decision logic of its own; it only exposes hooks that an external component (here, the GUI's Send panel, acting as the "component") must explicitly drive. Nothing happens autonomously — every step requires an external call.

This satisfies the SRS's requirement for two genuinely distinct architectures (not one hardcoded path with a flag), and the choice is visibly tagged in the log panel (`[agent-controlled]` / `[component-controlled]`) so it's directly observable during testing.

### 4.7 `MessageRouter` (§2.2.4 — mode selection)

Thin dispatcher: given a `mode` string (`"unicast" | "multicast" | "broadcast"`) from the Send panel, routes the outgoing message to the matching transport. This is the concrete FR that operationalizes the Product Function statement in §2.2.4 (Part 1 basis (b)).

---

## 5. Wire Message Format

All messages, regardless of transport, share one JSON schema:

```json
{
  "type": "unicast | multicast | broadcast",
  "sender_id": "A1",
  "sender_addr": "127.0.0.1:6001",
  "timestamp": "2026-09-08T12:00:00Z",
  "encrypted": true,
  "payload": "<plaintext, or base64 AES-GCM ciphertext if encrypted=true>"
}
```

- **TCP (unicast):** stream, so each message is prefixed with a 4-byte big-endian length before the JSON body; the reader loop reads exactly that many bytes before decoding.
- **UDP (multicast/broadcast):** each datagram is exactly one JSON message — UDP preserves message boundaries, so no framing is needed (payload must stay under the ~65KB UDP practical limit, which is not otherwise enforced — a boundary condition worth a Part 3 test case).

---

## 6. GUI Layer (`agent_gui/`)

Each `AgentWindow` (a `Toplevel`) wraps exactly one `AgentNode` and contains three panels:

- **Send panel** — mode selector (unicast/multicast/broadcast), target address+port (or group address+port), TTL field (multicast only), encrypt checkbox, Send button.
- **Group panel** — multicast group address/port entry, Join / Leave buttons, a live list of currently joined groups.
- **Log panel** — a scrolling, read-only text widget. Every event (sent, received, joined, left, encrypted, decrypted, error) is appended with a timestamp and, where relevant, the active conversation-control mode.

The GUI layer never calls `socket` directly — it only calls `AgentNode` methods and reads from its event queue.

---

## 7. Concurrency Model

Each transport owns independent listener thread(s):

| Thread | Owned by | Blocks on |
|---|---|---|
| TCP accept loop | `UnicastTransport` | `socket.accept()` |
| TCP handler (one per connection) | `UnicastTransport` | `socket.recv()` |
| Multicast recv loop (one per joined group) | `MulticastTransport` | `socket.recvfrom()` |
| Broadcast recv loop | `BroadcastTransport` | `socket.recvfrom()` |

None of these threads touch Tkinter widgets directly — **Tkinter is not thread-safe.** Every inbound event is pushed onto a thread-safe `queue.Queue` owned by `AgentNode`. `AgentWindow` polls that queue from the main thread via `root.after(100, self._poll)`, and only the main-thread poll callback updates the Log panel. This is the single most likely place for a naive implementation to introduce a cross-thread widget-access bug — worth checking first once code exists.

---

## 8. Requirement Traceability

| Part 1 Req. ID | Type | Component(s) |
|---|---|---|
| 3.2.1.1–3.2.1.4 | FR | `unicast.py` |
| 3.2.2.3–3.2.2.6 | FR | `multicast.py` (join/leave), `group_panel.py` |
| 3.2.2.1, 3.2.2.2, 3.2.2.7–3.2.2.9 | FR | `multicast.py` (send/config/multi-group recv) |
| 3.2.3.1, 3.2.3.2, 3.3.3.3 | FR | `broadcast.py` |
| 3.2.4.1–3.2.4.6 | FR | `crypto_service.py`, encrypt checkbox in `send_panel.py` |
| 3.2.5.1, 3.2.5.2 | FR | `conversation.py` |
| §2.2.4 | FR | `router.py`, mode selector in `send_panel.py` |
| §2.4.1 (Reliability) | NFR | `log_panel.py` (failures surfaced, never swallowed) |
| §2.4.2 (Security) | NFR | `crypto_service.py` |
| §2.4.3 / §2.4.4 (Portability) | NFR | `broadcast.py`, `multicast.py` (no cross-environment validation — documented limitation) |

---

## 9. Non-Goals

- No persistence (no database, no CRUD entities) — consistent with the "0 of 7 FRs are CRUD" finding in Part 1.
- No agent discovery/directory service.
- No production-grade key distribution — a single shared key at process start stands in for the SRS's conceptual key-distribution agent.
- No retry/acknowledgement logic for multicast/broadcast — best-effort delivery is an explicit SRS constraint (§2.4.1), not a gap to engineer around.

---

## 10. Traceability to Part 1 AI Assumptions

Every `(c) unsupported` assumption from Part 1 is deliberately **not "fixed"** in this architecture — it is implemented as-is and made observable (via the log panel) so it can be exercised and reported as a real finding in Part 3, rather than quietly resolved before testing ever sees it:

- Multicast join/leave timing (immediate/synchronous assumption)
- Multicast TTL default + loose address/port validation
- Broadcast sent without an OS-permission check
- Encryption algorithm/key management (AES-GCM, single shared key) as a concrete but unverified choice
- Delivery failures logged, not retried or acknowledged
- No cross-environment (multi-machine/network) validation performed
