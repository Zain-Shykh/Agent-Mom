"""Phase 0 stub: confirms Tkinter is available in this environment.
Will be replaced in Phase 13 by the real multi-window agent launcher.
"""
import tkinter as tk

if __name__ == "__main__":
    root = tk.Tk()
    root.title("agentMom GUI Baseline — Phase 0 smoke test")
    root.geometry("400x200")
    tk.Label(root, text="Tkinter is working.").pack(expand=True)
    root.mainloop()
