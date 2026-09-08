"""AgentWindow: one Toplevel per AgentNode (architecture.md §6).

Wires the queue-polling loop early since it's the thread-safety-critical
piece (architecture.md §7): AgentNode.poll_events() is only ever called
from this root.after() callback, on the main thread — no listener thread
touches a widget directly.
"""

import tkinter as tk
from tkinter import ttk

from agent_core.agent_node import AgentNode
from agent_core.conversation import AgentControlledConversation, ComponentControlledConversation
from agent_gui.group_panel import GroupPanel
from agent_gui.log_panel import LogPanel
from agent_gui.send_panel import SendPanel

POLL_INTERVAL_MS = 100

_CONTROLLER_FACTORIES = {
    "agent-controlled": AgentControlledConversation,
    "component-controlled": ComponentControlledConversation,
}


class AgentWindow(tk.Toplevel):
    def __init__(self, master, agent_node: AgentNode, **kwargs):
        super().__init__(master, **kwargs)
        self.agent_node = agent_node
        self.title(agent_node.agent_id)

        # Real panels are wired in Phases 10-12; each attribute stays None
        # until then, and _on_event() falls back to a temporary label.
        self.log_panel = None
        self.send_panel = None
        self.group_panel = None

        self._build_layout()
        self._poll()

    def _build_layout(self) -> None:
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)

        self._placeholder = ttk.Label(container, text=f"Agent {self.agent_node.agent_id}")
        self._placeholder.pack(padx=10, pady=(10, 0), anchor="w")

        mode_frame = ttk.Frame(container)
        mode_frame.pack(fill="x", padx=10, pady=(4, 0))
        ttk.Label(mode_frame, text="Conversation mode:").pack(side="left")
        initial_mode = (
            "agent-controlled"
            if isinstance(self.agent_node.conversation_controller, AgentControlledConversation)
            else "component-controlled"
        )
        self.mode_var = tk.StringVar(value=initial_mode)
        mode_combo = ttk.Combobox(
            mode_frame, textvariable=self.mode_var, values=list(_CONTROLLER_FACTORIES), state="readonly", width=20
        )
        mode_combo.pack(side="left", padx=(4, 0))
        mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)

        self.send_panel = SendPanel(container, self.agent_node)
        self.send_panel.pack(fill="x", padx=10, pady=(4, 0))

        self.group_panel = GroupPanel(container, self.agent_node)
        self.group_panel.pack(fill="x", padx=10, pady=(4, 0))

        self.log_panel = LogPanel(container)
        self.log_panel.pack(fill="both", expand=True, padx=10, pady=10)

    def _poll(self) -> None:
        for event in self.agent_node.poll_events():
            self._on_event(event)
        if self.group_panel is not None:
            self.group_panel.refresh()
        self.after(POLL_INTERVAL_MS, self._poll)

    def _on_mode_change(self, _event=None) -> None:
        """Swap the live ConversationController — architecture.md §4.6 requires
        two genuinely distinct implementations, not a flag on one class, so
        this replaces the instance outright rather than toggling a mode flag."""
        factory = _CONTROLLER_FACTORIES[self.mode_var.get()]
        self.agent_node.conversation_controller = factory()

    def _on_event(self, event) -> None:
        if self.log_panel is not None:
            self.log_panel.append(event)
        else:
            self._placeholder.config(text=f"Agent {self.agent_node.agent_id}: {event.detail}")
