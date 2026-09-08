"""MulticastTransport: UDP multicast group join/leave/send (3.2.2.1-3.2.2.9).

One dedicated recv-loop thread per joined group, all feeding the same
shared inbound queue.Queue supplied by the caller (AgentNode owns it in
the full system) so this module never touches Tkinter or any GUI code.

Per architecture.md §4.3, join/leave timing is an AI assumption flagged
(c) unsupported in Part 1: a message sent immediately after leave_group()
returns may or may not still be received, since the OS drops group
membership asynchronously relative to our thread teardown. This is left
as-is deliberately, not hardened, so Part 3 can probe it directly.
"""

import queue
import socket
import struct
import threading

from agent_core.message import Message

_RECV_BUF_SIZE = 65536  # UDP practical max datagram size; not otherwise enforced.


class MulticastTransport:
    def __init__(self, agent_id: str, inbound_queue: "queue.Queue[Message]"):
        self.agent_id = agent_id
        self.inbound_queue = inbound_queue

        # (addr, port) -> {"sock": socket.socket, "thread": threading.Thread, "stop_event": threading.Event}
        self.groups: dict[tuple[str, int], dict] = {}

    def join_group(self, addr: str, port: int) -> None:
        """Join a multicast group and start a recv thread for it."""
        if (addr, port) in self.groups:
            return  # already joined — no-op

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", port))

        mreq = struct.pack("4sl", socket.inet_aton(addr), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        # A blocking recvfrom() on another thread does not reliably unblock when
        # this socket is close()'d from leave_group() (a well-known Linux
        # threading pitfall), so the recv loop polls stop_event via a timeout.
        sock.settimeout(0.5)

        stop_event = threading.Event()
        thread = threading.Thread(target=self._recv_loop, args=(sock, stop_event), daemon=True)
        self.groups[(addr, port)] = {"sock": sock, "thread": thread, "stop_event": stop_event}
        thread.start()

    def leave_group(self, addr: str, port: int) -> None:
        """Leave a multicast group, stopping and joining its recv thread."""
        group = self.groups.pop((addr, port), None)
        if group is None:
            return  # not joined — no-op

        mreq = struct.pack("4sl", socket.inet_aton(addr), socket.INADDR_ANY)
        try:
            group["sock"].setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
        except OSError:
            pass  # socket may already be unusable — closing it below still tears the thread down

        group["stop_event"].set()
        group["sock"].close()
        group["thread"].join(timeout=2)

    def send(self, addr: str, port: int, message: Message, ttl: int = 1) -> None:
        """Send one datagram to a multicast group, with a per-send TTL."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
            sock.sendto(message.to_bytes(), (addr, port))
        finally:
            sock.close()

    def _recv_loop(self, sock: socket.socket, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                data, _addr = sock.recvfrom(_RECV_BUF_SIZE)
            except socket.timeout:
                continue  # no datagram within the poll interval — check stop_event again
            except OSError:
                # Socket was closed by leave_group() — exit the loop.
                break
            message = Message.from_bytes(data)
            self.inbound_queue.put(message)
