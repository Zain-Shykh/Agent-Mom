"""Core-layer smoke test (Phase 8) — exercises Phases 2-7 end-to-end with
real sockets and threads, no GUI. Run with: pytest tests/smoke_test_core.py
"""

import time

import pytest

from agent_core.agent_node import AgentNode
from agent_core.conversation import AgentControlledConversation, ComponentControlledConversation
from agent_core.crypto_service import CryptoService

UNICAST_PORTS = (7501, 7502, 7503)
BROADCAST_PORT = 7600
GROUP_ADDR, GROUP_PORT = "239.9.9.9", 7700


@pytest.fixture
def agents():
    crypto = CryptoService(CryptoService.generate_key())
    n1 = AgentNode("N1", UNICAST_PORTS[0], crypto, AgentControlledConversation(), broadcast_port=BROADCAST_PORT)
    n2 = AgentNode("N2", UNICAST_PORTS[1], crypto, ComponentControlledConversation(), broadcast_port=BROADCAST_PORT)
    n3 = AgentNode("N3", UNICAST_PORTS[2], crypto, ComponentControlledConversation(), broadcast_port=BROADCAST_PORT)
    try:
        yield n1, n2, n3
    finally:
        n1.stop()
        n2.stop()
        n3.stop()


def test_unicast_delivery_and_no_autonomous_reaction(agents):
    n1, n2, _n3 = agents
    n1.send("unicast", f"127.0.0.1:{UNICAST_PORTS[1]}", "hello N2")
    time.sleep(0.3)

    events = n2.poll_events()
    assert any(e.kind == "received" and e.detail.endswith("hello N2") for e in events)
    assert n2.poll_events() == []  # component-controlled: nothing happens without an external call


def test_agent_controlled_auto_ack(agents):
    n1, n2, _n3 = agents
    n2.send("unicast", f"127.0.0.1:{UNICAST_PORTS[0]}", "ping N1")
    time.sleep(0.3)

    kinds = [e.kind for e in n1.poll_events()]
    assert "received" in kinds
    assert "sent" in kinds  # the auto-ack, fired with no external drive


def test_multicast_group_delivery(agents):
    n1, n2, n3 = agents
    n2.join_group(GROUP_ADDR, GROUP_PORT)
    n3.join_group(GROUP_ADDR, GROUP_PORT)
    time.sleep(0.3)

    n1.send("multicast", f"{GROUP_ADDR}:{GROUP_PORT}", "group hello", ttl=1)
    time.sleep(0.3)

    for member in (n2, n3):
        events = member.poll_events()
        assert any(e.kind == "received" and "group hello" in e.detail for e in events)


def test_broadcast_delivery(agents):
    n1, n2, n3 = agents
    n1.send("broadcast", "", "broadcast hi")
    time.sleep(0.3)

    for member in (n2, n3):
        events = member.poll_events()
        assert any(e.kind == "received" and "broadcast hi" in e.detail for e in events)


def test_encrypted_unicast_auto_decrypts(agents):
    n1, n2, _n3 = agents
    n1.send("unicast", f"127.0.0.1:{UNICAST_PORTS[1]}", "secret payload", encrypt=True)
    time.sleep(0.3)

    events = n2.poll_events()
    kinds = [e.kind for e in events]
    assert "received" in kinds and "decrypted" in kinds
    assert any(e.kind == "decrypted" and "secret payload" in e.detail for e in events)
