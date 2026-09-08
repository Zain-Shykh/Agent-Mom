"""SendPanel: mode selector, target, TTL, encrypt checkbox, Send button
(architecture.md §6). The Send button only ever calls into AgentNode —
it never touches a socket directly.
"""

import tkinter as tk
from tkinter import ttk

from agent_core.agent_node import AgentNode

_MODES = ("unicast", "multicast", "broadcast")


class SendPanel(ttk.Frame):
    def __init__(self, master, agent_node: AgentNode, **kwargs):
        super().__init__(master, **kwargs)
        self.agent_node = agent_node

        self.mode_var = tk.StringVar(value=_MODES[0])
        self.target_var = tk.StringVar()
        self.ttl_var = tk.StringVar(value="1")
        self.encrypt_var = tk.BooleanVar(value=False)
        self.payload_var = tk.StringVar()

        ttk.Label(self, text="Mode:").grid(row=0, column=0, sticky="w")
        mode_combo = ttk.Combobox(self, textvariable=self.mode_var, values=_MODES, state="readonly", width=10)
        mode_combo.grid(row=0, column=1, sticky="w")
        mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_ttl_state())

        ttk.Label(self, text="Target (addr:port):").grid(row=1, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.target_var, width=24).grid(row=1, column=1, sticky="w")

        ttk.Label(self, text="TTL:").grid(row=2, column=0, sticky="w")
        self.ttl_entry = ttk.Entry(self, textvariable=self.ttl_var, width=6)
        self.ttl_entry.grid(row=2, column=1, sticky="w")

        ttk.Checkbutton(self, text="Encrypt", variable=self.encrypt_var).grid(row=3, column=0, sticky="w")

        ttk.Label(self, text="Payload:").grid(row=4, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.payload_var, width=30).grid(row=4, column=1, sticky="w")

        ttk.Button(self, text="Send", command=self._on_send).grid(row=5, column=0, columnspan=2, pady=(4, 0))

        self._update_ttl_state()

    def _update_ttl_state(self) -> None:
        # TTL only means anything for multicast (broadcast.py/unicast.py have no TTL concept).
        self.ttl_entry.configure(state="normal" if self.mode_var.get() == "multicast" else "disabled")

    def _on_send(self) -> None:
        mode = self.mode_var.get()
        target = self.target_var.get()
        payload = self.payload_var.get()
        encrypt = self.encrypt_var.get()

        ttl = None
        if mode == "multicast":
            try:
                ttl = int(self.ttl_var.get())
            except ValueError:
                ttl = 1  # matches MulticastTransport.send()'s own default — no stricter validation here either

        self.agent_node.send(mode, target, payload, ttl=ttl, encrypt=encrypt)
