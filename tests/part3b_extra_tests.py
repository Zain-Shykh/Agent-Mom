"""Part 3(b) evidence tests — boundary, invalid-input, and known-limitation
probes, run headless against agent_core (no tkinter/display needed).
Run with: venv/bin/python -m pytest tests/part3b_extra_tests.py -v
"""

import socket
import time

import pytest

from agent_core.agent_node import AgentNode
from agent_core.conversation import ComponentControlledConversation

UNICAST_PORTS = (7801, 7802, 7803)
BROADCAST_PORT = 7900
GROUP_ADDR, GROUP_PORT = "239.9.9.20", 7950


@pytest.fixture
def agents():
    from agent_core.crypto_service import CryptoService
    crypto = CryptoService(CryptoService.generate_key())
    n1 = AgentNode("N1", UNICAST_PORTS[0], crypto, ComponentControlledConversation(), broadcast_port=BROADCAST_PORT)
    n2 = AgentNode("N2", UNICAST_PORTS[1], crypto, ComponentControlledConversation(), broadcast_port=BROADCAST_PORT)
    try:
        yield n1, n2
    finally:
        n1.stop()
        n2.stop()


# --- TC-04: TTL boundary, minimum valid value ---
def test_ttl_min_valid_1(agents):
    n1, n2 = agents
    n2.join_group(GROUP_ADDR, GROUP_PORT)
    time.sleep(0.3)
    n1.send("multicast", f"{GROUP_ADDR}:{GROUP_PORT}", "ttl-min", ttl=1)
    time.sleep(0.3)
    events = n2.poll_events()
    assert any(e.kind == "received" and "ttl-min" in e.detail for e in events)


# --- TC-05: TTL boundary, maximum valid value (255 is the byte ceiling for IP_MULTICAST_TTL) ---
def test_ttl_max_valid_255(agents):
    n1, n2 = agents
    n2.join_group(GROUP_ADDR, GROUP_PORT)
    time.sleep(0.3)
    n1.send("multicast", f"{GROUP_ADDR}:{GROUP_PORT}", "ttl-max", ttl=255)
    time.sleep(0.3)
    events = n2.poll_events()
    assert any(e.kind == "received" and "ttl-max" in e.detail for e in events)


# --- TC-06: invalid TTL, out of range (256+) — expected: rejected gracefully; actual: crashes ---
def test_ttl_out_of_range_256_raises_unhandled_error(agents):
    n1, n2 = agents
    n2.join_group(GROUP_ADDR, GROUP_PORT)
    time.sleep(0.2)
    with pytest.raises(OSError):
        n1.send("multicast", f"{GROUP_ADDR}:{GROUP_PORT}", "ttl-over", ttl=999)


# --- TC-07: invalid TTL, negative value — documents that it is silently
# accepted (no validation) rather than rejected, which is itself the defect.
def test_ttl_negative_silently_accepted_and_delivered(agents):
    n1, n2 = agents
    n2.join_group(GROUP_ADDR, GROUP_PORT)
    time.sleep(0.2)
    # No exception should occur — this is the defect: invalid TTL is treated as valid.
    n1.send("multicast", f"{GROUP_ADDR}:{GROUP_PORT}", "ttl-negative", ttl=-1)
    time.sleep(0.3)
    events = n2.poll_events()
    assert any(e.kind == "received" and "ttl-negative" in e.detail for e in events), \
        "expected the (invalid) negative-TTL message to still be delivered, confirming no validation exists"


# --- TC-08: invalid multicast address (not in 224.0.0.0/4 multicast range) accepted with no validation ---
def test_non_multicast_address_not_rejected(agents):
    n1, _n2 = agents
    # 10.0.0.5 is a private unicast-range address, not a valid multicast address.
    # No exception should occur at the app layer (this documents the missing validation).
    n1.send("multicast", "10.0.0.5:7999", "should-be-rejected", ttl=1)


# --- TC-09: unicast to an unreachable/closed port surfaces an error event, not silent failure ---
def test_unicast_to_closed_port_logs_error_event(agents):
    n1, _n2 = agents
    closed_port = 7899  # nothing listening here
    with pytest.raises(ConnectionRefusedError):
        n1.send("unicast", f"127.0.0.1:{closed_port}", "into the void")
    events = n1.poll_events()
    assert any(e.kind == "error" for e in events), "expected an error Event, found none"


# --- TC-10: multicast leave-then-immediate-send timing (non-deterministic, per KNOWN_LIMITATIONS) ---
def test_leave_then_immediate_send_timing(agents):
    """Runs N trials and records how many times a message sent immediately
    after leave_group() returns is still received — expected (per the
    access-control rule in 3.2.2.5/3.2.2.6) is 0/N. Any nonzero count
    confirms the documented timing defect."""
    from agent_core.crypto_service import CryptoService
    trials = 5
    received_after_leave = 0
    for i in range(trials):
        crypto = CryptoService(CryptoService.generate_key())
        sender = AgentNode(f"S{i}", 7810 + i, crypto, ComponentControlledConversation(), broadcast_port=BROADCAST_PORT)
        member = AgentNode(f"M{i}", 7830 + i, crypto, ComponentControlledConversation(), broadcast_port=BROADCAST_PORT)
        try:
            member.join_group(GROUP_ADDR, GROUP_PORT + 1)
            time.sleep(0.2)
            member.leave_group(GROUP_ADDR, GROUP_PORT + 1)
            sender.send("multicast", f"{GROUP_ADDR}:{GROUP_PORT + 1}", f"post-leave-{i}", ttl=1)
            time.sleep(0.3)
            events = member.poll_events()
            if any(e.kind == "received" and f"post-leave-{i}" in e.detail for e in events):
                received_after_leave += 1
        finally:
            sender.stop()
            member.stop()
    print(f"\nReceived-after-leave: {received_after_leave}/{trials} trials")
    # Not asserted PASS/FAIL here on purpose — this test's *point* is to
    # measure and report the actual rate, used as evidence in the report,
    # not to enforce a pass.


# --- TC-09: agent subscribed to 2+ groups receives from each independently ---
def test_multi_group_simultaneous_receive(agents):
    n1, n2 = agents
    group_a = ("239.9.9.40", 7991)
    group_b = ("239.9.9.41", 7992)
    n2.join_group(*group_a)
    n2.join_group(*group_b)
    time.sleep(0.3)
    n1.send("multicast", f"{group_a[0]}:{group_a[1]}", "from-group-A", ttl=1)
    n1.send("multicast", f"{group_b[0]}:{group_b[1]}", "from-group-B", ttl=1)
    time.sleep(0.3)
    events = n2.poll_events()
    assert any(e.kind == "received" and "from-group-A" in e.detail for e in events)
    assert any(e.kind == "received" and "from-group-B" in e.detail for e in events)


# --- TC-12: a message that cannot be decrypted (wrong key) is handled
# gracefully — an error Event is queued, the app does not crash ---
def test_undecryptable_message_handled_gracefully(agents):
    from agent_core.crypto_service import CryptoService
    from agent_core.message import Message
    n1, n2 = agents
    wrong_key_crypto = CryptoService(CryptoService.generate_key())  # NOT n2's key
    bad_msg = Message(
        type="unicast", sender_id="N1", sender_addr="127.0.0.1:" + str(UNICAST_PORTS[0]),
        timestamp="2026-01-01T00:00:00Z", encrypted=True,
        payload=wrong_key_crypto.encrypt("secret"),
    )
    n2._inbound_msgs.put(bad_msg)
    time.sleep(0.3)
    events = n2.poll_events()
    assert any(e.kind == "error" and "decrypt" in e.detail for e in events), \
        "expected a graceful decrypt-failure error Event, found none (possible unhandled crash instead)"

