"""AgentNode: the central per-agent object (architecture.md §4.1).

Owns one instance of each transport, one CryptoService, one
ConversationController, and the raw inbound-message queue that every
transport's listener thread feeds. poll_events() is the single place
where inbound network traffic is turned into GUI-facing Events — no
background thread does this, so it's only ever safe to call from
Tkinter's main thread via root.after() (architecture.md §7): all the
decrypt / conversation-controller / auto-reply logic below runs
synchronously inside that call, never on a listener thread.
"""

import datetime
import queue
from dataclasses import dataclass

from agent_core.broadcast import BroadcastTransport
from agent_core.conversation import ConversationController
from agent_core.crypto_service import CryptoService
from agent_core.message import Message
from agent_core.multicast import MulticastTransport
from agent_core.router import MessageRouter
from agent_core.unicast import UnicastTransport

DEFAULT_BROADCAST_PORT = 6400  # shared across all agents, unlike each agent's own unicast port


@dataclass
class Event:
    kind: str  # "sent" | "received" | "joined" | "left" | "encrypted" | "decrypted" | "error"
    detail: str
    conversation_mode: "str | None" = None


class AgentNode:
    def __init__(
        self,
        agent_id: str,
        unicast_port: int,
        crypto_service: CryptoService,
        conversation_controller: ConversationController,
        host: str = "127.0.0.1",
        broadcast_port: int = DEFAULT_BROADCAST_PORT,
    ):
        self.agent_id = agent_id
        self.host = host
        self.unicast_port = unicast_port
        self.crypto_service = crypto_service
        self.conversation_controller = conversation_controller

        self._inbound_msgs: "queue.Queue[Message]" = queue.Queue()
        self.events: "queue.Queue[Event]" = queue.Queue()

        self.unicast = UnicastTransport(agent_id, unicast_port, self._inbound_msgs, host="0.0.0.0")
        self.multicast = MulticastTransport(agent_id, self._inbound_msgs)
        self.broadcast = BroadcastTransport(agent_id, broadcast_port, self._inbound_msgs)
        self.router = MessageRouter(self.unicast, self.multicast, self.broadcast)

        self.unicast.start()
        self.broadcast.start()

    def stop(self) -> None:
        self.unicast.stop()
        self.broadcast.stop()
        for addr, port in list(self.multicast.groups.keys()):
            self.multicast.leave_group(addr, port)

    def send(self, mode: str, target: str, payload: str, *, ttl: "int | None" = None, encrypt: bool = False) -> None:
        out_payload = payload
        if encrypt:
            out_payload = self.crypto_service.encrypt(payload)
            self.events.put(Event(kind="encrypted", detail=f"encrypted outbound payload for {mode} -> {target}"))

        message = Message(
            type=mode,
            sender_id=self.agent_id,
            sender_addr=f"{self.host}:{self.unicast_port}",
            timestamp=_now_iso(),
            encrypted=encrypt,
            payload=out_payload,
        )
        try:
            self.router.send(mode, target, message, ttl=ttl)
        except Exception as exc:
            # Delivery failures are logged, not retried or acknowledged
            # (architecture.md §10) — surfaced to the log panel and still
            # re-raised, never silently swallowed.
            self.events.put(Event(kind="error", detail=f"send failed for [{mode}] -> {target}: {exc}"))
            raise
        self.events.put(
            Event(
                kind="sent",
                detail=f"[{mode}] -> {target}: {payload}",
                conversation_mode=type(self.conversation_controller).__name__,
            )
        )

    def join_group(self, addr: str, port: int) -> None:
        self.multicast.join_group(addr, port)
        self.events.put(Event(kind="joined", detail=f"joined {addr}:{port}"))

    def leave_group(self, addr: str, port: int) -> None:
        self.multicast.leave_group(addr, port)
        self.events.put(Event(kind="left", detail=f"left {addr}:{port}"))

    def poll_events(self) -> "list[Event]":
        """Non-blocking: drain inbound network messages, run the
        conversation controller, then return everything queued for the GUI."""
        while True:
            try:
                msg = self._inbound_msgs.get_nowait()
            except queue.Empty:
                break
            self._process_inbound(msg)

        while True:
            action = self.conversation_controller.decide_next_action()
            if action is None:
                break
            target = f"{action.target_addr}:{action.target_port}"
            self.send(action.mode, target, action.payload, ttl=action.ttl, encrypt=action.encrypt)

        drained = []
        while True:
            try:
                drained.append(self.events.get_nowait())
            except queue.Empty:
                break
        return drained

    def _process_inbound(self, msg: Message) -> None:
        mode = type(self.conversation_controller).__name__
        self.events.put(
            Event(kind="received", detail=f"[{msg.type}] from {msg.sender_id}: {msg.payload}", conversation_mode=mode)
        )

        plaintext = msg.payload
        if msg.encrypted:
            try:
                plaintext = self.crypto_service.decrypt(msg.payload)
                self.events.put(Event(kind="decrypted", detail=f"decrypted payload from {msg.sender_id}: {plaintext}"))
            except Exception as exc:
                self.events.put(Event(kind="error", detail=f"decrypt failed for message from {msg.sender_id}: {exc}"))
                return

        decrypted_msg = Message(
            type=msg.type,
            sender_id=msg.sender_id,
            sender_addr=msg.sender_addr,
            timestamp=msg.timestamp,
            encrypted=msg.encrypted,
            payload=plaintext,
        )
        self.conversation_controller.on_message_received(decrypted_msg)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
