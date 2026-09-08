"""GroupPanel: multicast group join/leave UI (architecture.md §6).

The joined-groups list is rebuilt straight from
`agent_node.multicast.groups` on every refresh — it is never independent
UI-only state, so it can't drift from what the transport actually has
joined.
"""

import tkinter as tk
from tkinter import ttk

from agent_core.agent_node import AgentNode


class GroupPanel(ttk.Frame):
    def __init__(self, master, agent_node: AgentNode, **kwargs):
        super().__init__(master, **kwargs)
        self.agent_node = agent_node

        self.addr_var = tk.StringVar()
        self.port_var = tk.StringVar()

        ttk.Label(self, text="Group addr:").grid(row=0, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.addr_var, width=16).grid(row=0, column=1, sticky="w")
        ttk.Label(self, text="Port:").grid(row=0, column=2, sticky="w")
        ttk.Entry(self, textvariable=self.port_var, width=6).grid(row=0, column=3, sticky="w")

        ttk.Button(self, text="Join", command=self._on_join).grid(row=0, column=4, padx=(4, 0))
        ttk.Button(self, text="Leave", command=self._on_leave).grid(row=0, column=5, padx=(4, 0))

        ttk.Label(self, text="Joined groups:").grid(row=1, column=0, columnspan=6, sticky="w", pady=(4, 0))
        self.groups_list = tk.Listbox(self, height=3)
        self.groups_list.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(0, 4))

        self.refresh()

    def _on_join(self) -> None:
        addr, port = self.addr_var.get(), self.port_var.get()
        if not addr or not port:
            return
        self.agent_node.join_group(addr, int(port))
        self.refresh()

    def _on_leave(self) -> None:
        addr, port = self.addr_var.get(), self.port_var.get()
        if not addr or not port:
            return
        self.agent_node.leave_group(addr, int(port))
        self.refresh()

    def refresh(self) -> None:
        """Re-read AgentNode's real joined-group state, not cached UI state."""
        current = {f"{addr}:{port}" for addr, port in self.agent_node.multicast.groups.keys()}
        shown = set(self.groups_list.get(0, "end"))
        if current != shown:
            self.groups_list.delete(0, "end")
            for entry in sorted(current):
                self.groups_list.insert("end", entry)
