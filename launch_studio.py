"""Entry point for the portable Windows build."""
import logging
from pathlib import Path
import os

from convovault.gui.server import main


if __name__ == "__main__":
    try:
        main()
    except Exception:
        location = Path(os.environ.get("APPDATA", Path.home())) / "convovault" / "studio-error.log"
        location.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=location, level=logging.ERROR, force=True)
        logging.exception("Studio could not start")
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("ConvoVault Studio", f"Studio could not start. Details were saved to:\n{location}")
        root.destroy()
