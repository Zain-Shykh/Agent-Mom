# Part 3A — SonarQube Report and NFR Evaluation

Scan target: complete frozen baseline (`part2_gui_baseline/`, commit `09403cc`,
tooling committed at `f131ba7`). SonarQube Community Build 26.9.0 (Docker),
scanned with `sonar-scanner-cli` against project key `agentmom-part2-baseline`.
Dashboard: `http://localhost:9000/dashboard?id=agentmom-part2-baseline`.

## Overall report summary (Context)

| Metric | Value |
|---|---|
| Quality Gate | Passed |
| Lines of code | 597 (15 Python files) |
| Bugs / Reliability rating | 0 / A |
| Vulnerabilities / Security rating | 0 / A |
| Security Hotspots | 0 |
| Code Smells / Maintainability rating | 3 (Minor) / A, 11 min remediation effort |
| Duplicated lines | 0.0% |
| Coverage | 61.7% (agent_core 91–100%, agent_gui 0%) |
| Complexity / Cognitive complexity | 98 / 70 |

## Evidence (screenshots from the SonarQube dashboard)

- `evidence/part3a_sonarqube_overview.png` — Projects overview: Quality Gate **Passed**, 597 LOC, Security A (0), Reliability A (0), Maintainability A (3), 61.7% coverage, 0.0% duplication. Confirms the scan ran against the complete project (`AgentMom Part 2 GUI Baseline`, public, Python), not a subset.
- `evidence/part3a_sonarqube_issues.png` — Issues list: all 3 open Code Smells, each showing file, line, rule message, effort, and "19 hours ago" (i.e. persisted from the actual scan run, not fabricated) — matches the 3 findings interpreted below exactly (`agent_node.py` L65, `unicast.py` L70, `unicast.py` L75).

## Five selected findings, interpreted

### 1. `agent_core/agent_node.py:65` — "Remove this unnecessary `list()` call" (rule `python:S7504`, Minor, Maintainability)

- **What SonarQube reported**: the `list()` wrapper around `self.multicast.groups.keys()` in `AgentNode.stop()` is flagged as redundant, since the loop only needs to iterate the keys once.
- **Where**: `stop()`, line 65 — `for addr, port in list(self.multicast.groups.keys()): self.multicast.leave_group(addr, port)`.
- **Why it matters**: taken at face value the rule is correct in the general case — wrapping an already-iterable object in `list()` is usually pointless. But here, `leave_group()` **deletes** the entry from `self.multicast.groups` on every iteration. Without `list()`, this becomes `RuntimeError: dictionary changed size during iteration`, i.e. a genuine, reproducible crash on shutdown with 2+ joined groups.
- **What action the evidence supports**: **do not apply the suggested fix.** This is a case where the static rule's generic pattern-match doesn't see the mutation happening inside the called method, and a naive auto-fix would introduce a real bug. Recorded here as a defensible "no action" decision, not an oversight.

### 2. `agent_core/unicast.py:70` — "Remove this redundant Exception class; it derives from another which is already caught" (rule `python:S5713`, Minor, Maintainability)

- **What SonarQube reported**: `except (ConnectionError, ValueError, OSError):` in `_handle_connection()` lists `ConnectionError`, but `ConnectionError` is a subclass of `OSError`, which is also in the same tuple — so it's caught twice, redundantly.
- **Where**: `_handle_connection()`, line 70.
- **Why it matters**: unlike Finding 1, this one is a legitimate simplification with zero behavioral risk — `except (ValueError, OSError):` catches exactly the same exceptions.
- **What action the evidence supports**: a legitimate, low-risk simplification — but per the assignment's freeze rule ("keep the baseline unchanged while collecting SonarQube and test evidence... preserve the evaluated baseline separately" if fixed later), this should **not** be applied to the frozen baseline now, since that would invalidate the 1:1 correspondence between this report and commit `09403cc`/`f131ba7`. Record it as a confirmed, low-severity, easy-to-fix finding; apply it only in a post-evaluation commit if the pair chooses to demonstrate remediation, keeping the evaluated snapshot separately preserved.

### 3. `agent_core/unicast.py:75` — "Add logic to this except clause or eliminate it and rethrow the exception automatically" (rule `python:S2737`, Minor, Maintainability)

- **What SonarQube reported**: the `except (ConnectionError, ValueError, OSError): raise` block in `_handle_connection()` does nothing but re-raise, which the rule treats as pointless — Python would do the same thing if the `try/except` weren't there at all.
- **Where**: `_handle_connection()`, line 75. The surrounding code comment explains the intent: letting the exception propagate out of the listener thread causes Python's default thread behavior to print the traceback to stderr, which is the mechanism relied on to satisfy "failures surfaced, never silently swallowed" (architecture.md §8, tied to NFR1 §2.4.1).
- **Why it matters**: this is a case where a generic maintainability rule conflicts with a deliberate architecture decision. Removing the `except` block would produce identical runtime behavior — but would strip the inline documentation explaining *why* failures aren't handled here, which is exactly the kind of AI-introduced assumption this assignment asks pairs to keep visible rather than hide.
- **What action the evidence supports**: no functional change; if anything, strengthen the comment (already present) rather than delete the block, since a future reader (or SonarQube re-run) needs the explanation to be legible without conversation history.

### 4. Zero Bugs, zero Vulnerabilities, zero Security Hotspots (Reliability & Security ratings, both A)

- **What SonarQube reported**: no BUG-type or VULNERABILITY-type issues, and no Security Hotspots requiring manual review, across the whole 597-line codebase including `crypto_service.py` (AES-256-GCM key/nonce handling) and the raw-socket code (`SO_REUSEADDR`, `SO_BROADCAST`, `0.0.0.0` binding).
- **Where**: whole-project rating, not a single file.
- **Why it matters**: this is a real, useful signal — no *known* insecure pattern (hardcoded secret literal, banned crypto primitive, SQL/command injection, etc.) matched anywhere. But it is not proof the encryption design is actually strong: SonarQube's rule set checks for known anti-patterns, not correctness of a specific protocol design. It cannot detect, for example, that the AES key is generated once per process with no rotation or out-of-band distribution (a real limitation, already recorded in `KNOWN_LIMITATIONS.md` item 4/6) — that's a design-level gap, not a pattern a static analyzer flags.
- **What action the evidence supports**: report the clean result as genuine but bounded evidence for NFR2 (Security) — supports "no obviously bad implementation pattern," not "cryptographically sound." No fix needed from Sonar's side; the actual limitation (key management) is out of static analysis's reach and must be reported as a scope limitation instead (see NFR table below).

### 5. Coverage 61.7% blended, but 91–100% in `agent_core/` vs 0% in `agent_gui/`

- **What SonarQube reported**: overall project coverage of 61.7%, computed from the `pytest --cov` run fed into the scan.
- **Where**: whole-project measure, with the per-directory breakdown visible in the Measures tab.
- **Why it matters**: the blended number alone would look like "worse than two-thirds of the app is tested," which is misleading. The split reflects the project's deliberate two-tier testing strategy (architecture.md's core/GUI split): `agent_core/` (sockets, crypto, routing, conversation logic) is unit-tested via `pytest` and sits at 91–100%; `agent_gui/` (Tkinter widgets) was verified manually and via system-level scripted interaction in Phases 9–14, which `pytest`/coverage.py cannot observe since it isn't exercised through the automated suite.
- **What action the evidence supports**: report the number with this context rather than at face value — it's evidence *for* the maintainability/testability of `agent_core` specifically, and a legitimate limitation (not a defect) that `agent_gui` has no automated coverage. This also directly motivates why Part 3B's manual system-level test cases exist — they're the actual test evidence for the 0%-covered GUI layer.

## NFR Evaluation Table

| NFR | SonarQube evidence (if relevant) | Other evaluation method | Finding / judgment | Limitation |
|---|---|---|---|---|
| **NFR1 — Reliability** (§2.4.1): multicast/broadcast delivery is best-effort; a message may reach all, some, or none of the intended recipients, and the SRS does not require retry/ack. | 0 Bugs (rating A) — no reliability defects flagged in the transport/routing code. Sonar cannot evaluate the *design* of best-effort delivery, only code-level defects. | Manual fault-injection test executed in Phase 14 (send to a closed port): reproduced a real gap where `AgentNode.send()` initially had no path to surface a delivery failure to the log panel at all — a bare `ConnectionRefusedError` with no `ERROR` event. This was fixed during Part 2 (see `KNOWN_LIMITATIONS.md` item 5) by adding an explicit `error` Event before re-raising. Also independently reproduced the SRS-consistent async multicast leave/receive race (item 1) — timing-dependent, not deterministic. | Best-effort delivery itself is SRS-compliant by design. The silent-failure risk the AI assumption predicted **did occur once during development** and was caught and fixed before freeze — worth reporting as evidence the assumption was real, not hypothetical. Current baseline logs (not retries/acks) all delivery failures, matching intended design. | Only one client/server pair and only loopback/local-subnet conditions were exercised; no test of delivery under real packet loss, congestion, or a genuinely unreachable third agent on a different host. |
| **NFR2 — Security**: encryption is applied to payloads, but the SRS gives no guarantee against a capable attacker decrypting messages. | 0 Vulnerabilities, 0 Security Hotspots, Security rating A across `crypto_service.py` and the socket layer — no known-bad pattern (hardcoded key, banned primitive, injection) detected. | Manual code review of `crypto_service.py`: confirms AES-256-GCM via the standard `cryptography` library (not a hand-rolled cipher), 12-byte random nonce per message, authenticated encryption (tag verified on decrypt — wrong-key decrypt raises `InvalidTag`, confirmed in Phase 5 testing). | The implementation uses an industry-standard authenticated cipher correctly for single-message confidentiality/integrity. However, the key is generated once per process and shared in-memory across all simulated agents with no rotation and no real key-distribution mechanism — this stands in for the SRS's undefined "key-distribution agent" and was never claimed as production-grade key management. | No independent cryptographic audit was performed (e.g. no nonce-reuse-under-rotation testing, since there is no rotation to test). SonarQube's clean result should not be read as a security guarantee — it only rules out known anti-patterns, not protocol-level weaknesses like the missing key distribution. |
| **NFR3 — Portability / environment dependency**: multicast needs router/NIC/OS multicast support; broadcast may need elevated OS permissions depending on the network. | Not applicable — SonarQube performs static analysis of source code and cannot evaluate cross-machine or cross-network behavior. | Structured inspection / scope statement: every phase of Part 2 (unicast, multicast, broadcast, GUI) was verified on exactly one Ubuntu Linux machine, over `127.0.0.1` and one local subnet. No OS-permission pre-check exists in `broadcast.py` (confirmed by code inspection, `KNOWN_LIMITATIONS.md` item 3) — broadcast succeeded in every run in this environment, which is consistent with, but does not prove, that it will succeed on a more restrictive network. | No portability defect was found, but none could be — because the required cross-environment condition was never exercised. This must be reported as an explicit scope limitation, not a "pass." | Single-machine, single-network validation only. No multi-host, multi-NIC, restrictive-firewall, or elevated-permission-required environment was tested. Do not report NFR3 as "verified portable." |
