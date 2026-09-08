"""UnicastTransport: TCP point-to-point send/receive (3.2.1.1-3.2.1.4).

One accept-loop listener thread per agent, one short-lived handler thread
per inbound connection. Inbound messages are pushed onto a queue.Queue
supplied by the caller (AgentNode owns it in the full system) so this
module never touches Tkinter or any GUI code.
"""

import queue
import socket
import threading

from agent_core.message import Message, pack_frame, read_frame


class UnicastTransport:
    def __init__(self, agent_id: str, port: int, inbound_queue: "queue.Queue[Message]", host: str = "0.0.0.0"):
        self.agent_id = agent_id
        self.port = port
        self.host = host
        self.inbound_queue = inbound_queue

        self._server_sock: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen()
        # A blocking accept() on another thread does not reliably unblock when
        # this socket is close()'d from stop() (a well-known Linux threading
        # pitfall), so the accept loop polls _stop_event via a timeout instead
        # of relying on close() to interrupt it.
        self._server_sock.settimeout(0.5)

        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_sock is not None:
            self._server_sock.close()
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2)

    def send(self, target_addr: str, target_port: int, message: Message) -> None:
        """Open a new TCP connection, write one framed message, close."""
        with socket.create_connection((target_addr, target_port)) as sock:
            sock.sendall(pack_frame(message.to_bytes()))

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                conn, addr = self._server_sock.accept()
            except socket.timeout:
                continue  # no connection within the poll interval — check _stop_event again
            except OSError:
                # Listener socket was closed by stop() — exit the loop.
                break
            handler = threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True)
            handler.start()

    def _handle_connection(self, conn: socket.socket, addr) -> None:
        try:
            frame = read_frame(conn)
            message = Message.from_bytes(frame)
            self.inbound_queue.put(message)
        except (ConnectionError, ValueError, OSError):
            # Deliberately not swallowed: default thread behavior prints the
            # traceback to stderr, satisfying "failures surfaced, never
            # swallowed" (architecture.md §8, NFR §2.4.1) without inventing
            # a GUI-facing error event format ahead of the log panel (Phase 10).
            raise
        finally:
            conn.close()
