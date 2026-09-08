"""LogPanel: read-only, auto-scrolling event log (architecture.md §6).

Every AgentNode Event is appended with a timestamp, a distinct label per
event kind, and — where relevant — the active conversation-control mode,
so the two ConversationController strategies are directly observable
during testing (architecture.md §4.6).
"""

import datetime
import tkinter as tk
from tkinter import ttk

_KIND_LABEL = {
    "sent": "SENT",
    "received": "RECV",
    "joined": "JOINED",
    "left": "LEFT",
    "encrypted": "ENCRYPTED",
    "decrypted": "DECRYPTED",
    "error": "ERROR",
}

_KIND_COLOR = {
    "sent": "#1a73e8",
    "received": "#188038",
    "joined": "#7b1fa2",
    "left": "#7b1fa2",
    "encrypted": "#e37400",
    "decrypted": "#e37400",
    "error": "#d93025",
}


class LogPanel(ttk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.text = tk.Text(self, height=14, state="disabled", wrap="word")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for kind, color in _KIND_COLOR.items():
            self.text.tag_configure(kind, foreground=color)

    def append(self, event) -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        label = _KIND_LABEL.get(event.kind, event.kind.upper())
        mode_suffix = f" ({event.conversation_mode})" if event.conversation_mode else ""
        line = f"[{timestamp}] {label}{mode_suffix}: {event.detail}\n"

        self.text.configure(state="normal")
        self.text.insert("end", line, (event.kind,))
        self.text.see("end")
        self.text.configure(state="disabled")
