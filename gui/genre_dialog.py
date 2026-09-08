"""Dialog to correct an album's filing genre."""

from __future__ import annotations

from typing import List, Optional, Tuple

import tkinter as tk
from tkinter import ttk

from gui.constants import FONT_LG, FONT_MD, FONT_SEGOE_UI, FONT_SM, FONT_XS


def prompt_edit_genre(
    parent,
    *,
    album_label: str,
    current: str,
    suggestions: List[str],
    has_override: bool,
    colors: dict,
) -> Optional[Tuple[str, str]]:
    """Return ('save', text), ('reset', ''), or None if cancelled."""
    bg = colors.get("panel", "#16213e")
    fg = colors.get("text", "#eaeaea")
    accent = colors.get("accent", "#6c63ff")
    btn_bg = colors.get("button_bg", accent)
    btn_fg = colors.get("button_fg", "#ffffff")
    muted = colors.get("muted", "#9ca3af")
    entry_bg = colors.get("panel2", bg)

    result: dict = {"value": None}

    win = tk.Toplevel(parent)
    win.title("Edit genre")
    win.transient(parent)
    win.resizable(False, False)
    win.configure(bg=bg)
    win.withdraw()

    outer = tk.Frame(win, bg=bg, padx=24, pady=20)
    outer.pack(fill="both", expand=True)

    tk.Label(
        outer,
        text=album_label,
        font=(FONT_SEGOE_UI, FONT_LG, "bold"),
        bg=bg,
        fg=fg,
        wraplength=410,
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(0, 8))

    tk.Label(
        outer,
        text="Shelf filing uses the first genre. Extra genres: Jazz; Rock",
        font=(FONT_SEGOE_UI, FONT_XS),
        bg=bg,
        fg=muted,
        wraplength=410,
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(0, 8))

    combo = ttk.Combobox(outer, values=suggestions, font=(FONT_SEGOE_UI, FONT_MD))
    combo.pack(fill="x", pady=(4, 20), ipady=6)
    combo.set(current)
    combo.focus_set()

    btn_row = tk.Frame(outer, bg=bg)
    btn_row.pack(fill="x")

    def finish(action: str, text: str = "") -> None:
        result["value"] = (action, text)
        win.destroy()

    def on_save() -> None:
        finish("save", combo.get().strip())

    def on_reset() -> None:
        finish("reset", "")

    tk.Button(
        btn_row,
        text="Save",
        command=on_save,
        font=(FONT_SEGOE_UI, FONT_SM),
        bg=accent,
        fg=btn_fg,
        activebackground=btn_bg,
        activeforeground=btn_fg,
        relief="groove",
        width=10,
    ).pack(side="right", ipady=6)

    tk.Button(
        btn_row,
        text="Cancel",
        command=win.destroy,
        font=(FONT_SEGOE_UI, FONT_SM),
        bg=btn_bg,
        fg=btn_fg,
        activebackground=accent,
        activeforeground=btn_fg,
        relief="groove",
        width=10,
    ).pack(side="right", padx=(0, 8), ipady=6)

    if has_override:
        tk.Button(
            btn_row,
            text="Reset to original",
            command=on_reset,
            font=(FONT_SEGOE_UI, FONT_SM),
            bg=entry_bg,
            fg=fg,
            activebackground=btn_bg,
            activeforeground=btn_fg,
            relief="groove",
        ).pack(side="left", ipady=6)

    win.update_idletasks()
    width = max(480, win.winfo_reqwidth(), outer.winfo_reqwidth() + 32)
    height = max(300, win.winfo_reqheight(), outer.winfo_reqheight() + 56)
    win.minsize(width, height)
    x = (win.winfo_screenwidth() // 2) - (width // 2)
    y = (win.winfo_screenheight() // 2) - (height // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")
    win.deiconify()
    win.lift()
    win.grab_set()
    win.bind("<Return>", lambda *_: on_save())
    win.bind("<Escape>", lambda *_: win.destroy())
    combo.focus_set()
    win.wait_window()
    return result["value"]
