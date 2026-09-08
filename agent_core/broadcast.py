"""BroadcastTransport: UDP subnet broadcast send/receive (3.2.3.1-3.3.3.3).

One UDP socket with SO_BROADCAST enabled for sending, and one recv-loop
thread bound to the broadcast port for receiving. Inbound messages are
pushed onto a queue.Queue supplied by the caller (AgentNode owns it in
the full system) so this module never touches Tkinter or any GUI code.

Per architecture.md §4.4, no OS-permission check is performed before
sending — this directly instantiates the Part 1 (c) assumption ("assumes
unrestricted broadcast permission," contradicting NFR §2.4.4). If the OS
denies the send, sendto() raises OSError/PermissionError naturally; this
is deliberately left uncaught here so it surfaces (stderr traceback today,
the log panel in Phase 10) rather than being silently swallowed.
"""

import queue
import socket
import threading

from agent_core.message import Message

_RECV_BUF_SIZE = 65536  # UDP practical max datagram size; not otherwise enforced.

BROADCAST_ADDR = "255.255.255.255"


class BroadcastTransport:
    def __init__(self, agent_id: str, port: int, inbound_queue: "queue.Queue[Message]"):
        self.agent_id = agent_id
        self.port = port
        self.inbound_queue = inbound_queue

        self._recv_sock: socket.socket | None = None
        self._recv_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._recv_sock.bind(("", self.port))

        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._recv_sock is not None:
            self._recv_sock.close()
        if self._recv_thread is not None:
            self._recv_thread.join(timeout=2)

    def send(self, message: Message, port: int | None = None) -> None:
        """Broadcast one datagram to the subnet. No permission pre-check —
        if the OS denies it, sendto() raises naturally rather than being
        caught and swallowed here (architecture.md §4.4).
        """
        target_port = port if port is not None else self.port
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(message.to_bytes(), (BROADCAST_ADDR, target_port))
        finally:
            sock.close()

    def _recv_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                data, _addr = self._recv_sock.recvfrom(_RECV_BUF_SIZE)
            except OSError:
                # Listener socket was closed by stop() — exit the loop.
                break
            message = Message.from_bytes(data)
            self.inbound_queue.put(message)
