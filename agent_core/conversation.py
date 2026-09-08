"""ConversationController strategy: agent-controlled vs component-controlled
conversation architectures (3.2.5.1 / 3.2.5.2), per architecture.md §4.6.

Two genuinely separate implementations, not one flag-driven path, because
the SRS requires both architectures to exist independently:

- AgentControlledConversation: decision logic lives inside the controller
  itself — on receiving a message it autonomously queues an auto-ack,
  entirely independent of the GUI. The agent "owns" the conversation.
- ComponentControlledConversation: the controller holds no decision logic
  of its own — nothing happens autonomously; every step requires an
  explicit external call (here, the GUI's Send panel, acting as the
  "component").

Whatever periodically drives the agent (AgentNode, polled by the GUI) calls
decide_next_action() and, if it returns an Action, executes it via the
router — this is what makes AgentControlledConversation's auto-ack visible
without the GUI ever deciding to send it.
"""

import collections
from abc import ABC, abstractmethod
from dataclasses import dataclass

from agent_core.message import Message

_AUTO_ACK_PREFIX = "ACK:"  # marks an auto-ack payload so it doesn't trigger a further auto-ack


@dataclass
class Action:
    mode: str  # "unicast" | "multicast" | "broadcast"
    target_addr: str
    target_port: int
    payload: str
    encrypt: bool = False
    ttl: int | None = None


class ConversationController(ABC):
    @abstractmethod
    def on_message_received(self, msg: Message) -> None: ...

    @abstractmethod
    def decide_next_action(self) -> "Action | None": ...


class AgentControlledConversation(ConversationController):
    """Autonomously auto-acknowledges every non-ack message it receives."""

    def __init__(self):
        self._pending_actions: "collections.deque[Action]" = collections.deque()

    def on_message_received(self, msg: Message) -> None:
        if msg.payload.startswith(_AUTO_ACK_PREFIX):
            return  # don't ack an ack — avoids an infinite ack loop

        target_addr, _, target_port = msg.sender_addr.partition(":")
        self._pending_actions.append(
            Action(
                mode="unicast",
                target_addr=target_addr,
                target_port=int(target_port),
                payload=f"{_AUTO_ACK_PREFIX}{msg.payload}",
            )
        )

    def decide_next_action(self) -> "Action | None":
        if not self._pending_actions:
            return None
        return self._pending_actions.popleft()


class ComponentControlledConversation(ConversationController):
    """No autonomous behavior; every send must be driven externally (the GUI)."""

    def on_message_received(self, msg: Message) -> None:
        pass  # observed by whatever logs it (log panel); no decision made here

    def decide_next_action(self) -> "Action | None":
        return None
