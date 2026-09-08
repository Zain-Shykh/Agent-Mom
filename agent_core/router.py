"""MessageRouter: mode -> transport dispatch (architecture.md §4.7).

Thin dispatcher operationalizing the mode selector in the Send panel —
no logic beyond picking the right transport lives here.
"""

from agent_core.broadcast import BroadcastTransport
from agent_core.message import Message
from agent_core.multicast import MulticastTransport
from agent_core.unicast import UnicastTransport


class MessageRouter:
    def __init__(self, unicast: UnicastTransport, multicast: MulticastTransport, broadcast: BroadcastTransport):
        self.unicast = unicast
        self.multicast = multicast
        self.broadcast = broadcast

    def send(self, mode: str, target: str, message: Message, *, ttl: "int | None" = None) -> None:
        """`target` is 'addr:port' for unicast/multicast; ignored for broadcast."""
        if mode == "unicast":
            addr, _, port = target.partition(":")
            self.unicast.send(addr, int(port), message)
        elif mode == "multicast":
            addr, _, port = target.partition(":")
            self.multicast.send(addr, int(port), message, ttl=ttl if ttl is not None else 1)
        elif mode == "broadcast":
            self.broadcast.send(message)
        else:
            raise ValueError(f"unknown mode: {mode!r}")
