"""Multi-window agent launcher (architecture.md §3, final form of the Phase 0 stub).

Generates one shared AES key, then spawns N AgentWindows, each wrapping its
own AgentNode on a unique unicast port. All agents share the same
broadcast port (broadcast has no per-agent addressing — see broadcast.py)
and the same multicast group addresses/ports, entered directly in each
window's Group panel.
"""

import tkinter as tk

from agent_core.agent_node import AgentNode
from agent_core.conversation import ComponentControlledConversation
from agent_core.crypto_service import CryptoService
from agent_gui.agent_window import AgentWindow

NUM_AGENTS = 3
BASE_UNICAST_PORT = 6001
BROADCAST_PORT = 6400


def build_agents(num_agents: int = NUM_AGENTS, base_port: int = BASE_UNICAST_PORT, broadcast_port: int = BROADCAST_PORT):
    """Create `num_agents` AgentNodes sharing one crypto key, on consecutive
    unicast ports starting at `base_port`. Every agent starts component-controlled
    — the per-window dropdown in AgentWindow can switch it at runtime.
    """
    crypto = CryptoService(CryptoService.generate_key())
    return [
        AgentNode(
            f"A{i + 1}",
            base_port + i,
            crypto,
            ComponentControlledConversation(),
            broadcast_port=broadcast_port,
        )
        for i in range(num_agents)
    ]


def build_windows(root: tk.Tk, nodes: "list[AgentNode]") -> "list[AgentWindow]":
    windows = []
    for i, node in enumerate(nodes):
        win = AgentWindow(root, node)
        win.geometry(f"+{100 + i * 420}+100")
        win.protocol("WM_DELETE_WINDOW", lambda n=node, w=win: (n.stop(), w.destroy()))
        windows.append(win)
    return windows


def main() -> None:
    root = tk.Tk()
    root.withdraw()  # no window of its own — it only owns the Toplevels

    nodes = build_agents()
    build_windows(root, nodes)

    root.mainloop()


if __name__ == "__main__":
    main()
