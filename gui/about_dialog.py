"""About / Help dialog."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox

from core.paths import project_root
from core.update_checker import check_for_update
from core.version import (
    APP_NAME,
    DISCOGS_DISCLAIMER,
    FEEDBACK_MAILTO,
    PURCHASE_URL,
    SUPPORT_EMAIL,
    __version__,
)


class AboutDialog:
    def __init__(self, parent) -> None:
        self.top = ctk.CTkToplevel(parent)
        self.top.title(f"About {APP_NAME}")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.geometry("480x420")
        self.top.resizable(False, False)

        body = ctk.CTkFrame(self.top, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(body, text=APP_NAME, font=("Segoe UI Semibold", 22)).pack(anchor="w")
        ctk.CTkLabel(body, text=f"Version {__version__}", font=("Segoe UI", 14), text_color="#94a3b8").pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(
            body,
            text=(
                "Organize your Discogs vinyl collection for physical shelves.\n"
                f"{DISCOGS_DISCLAIMER}\n\n"
                "Audio previews may use iTunes, Deezer, or Discogs-linked YouTube."
            ),
            justify="left",
            wraplength=420,
            font=("Segoe UI", 13),
        ).pack(anchor="w", pady=(0, 12))

        links = ctk.CTkFrame(body, fg_color="transparent")
        links.pack(fill="x", pady=(0, 12))

        for label, path in (
            ("Privacy Policy", "PRIVACY.md"),
            ("Terms of Use", "TERMS.md"),
        ):
            p = project_root() / path
            if p.exists():
                ctk.CTkButton(
                    links,
                    text=label,
                    width=140,
                    command=lambda fp=p: self._open_file(fp),
                ).pack(side="left", padx=(0, 8))

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(btns, text="Check for updates", command=self._check_updates).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="Send feedback", command=lambda: webbrowser.open(FEEDBACK_MAILTO)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="Close", command=self.top.destroy).pack(side="right")

        ctk.CTkLabel(body, text=f"Support: {SUPPORT_EMAIL}", font=("Segoe UI", 12), text_color="#64748b").pack(anchor="w", pady=(16, 0))

    def _open_file(self, path: Path) -> None:
        import os
        import platform
        import subprocess

        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except Exception as exc:
            messagebox.showerror("Open file", str(exc), parent=self.top)

    def _check_updates(self) -> None:
        info = check_for_update()
        if not info:
            messagebox.showinfo("Updates", "You are on the latest version.", parent=self.top)
            return
        msg = f"Version {info.latest_version} is available."
        if info.release_notes:
            msg += f"\n\n{info.release_notes}"
        if info.download_url:
            msg += f"\n\nDownload: {info.download_url}"
        if messagebox.askyesno("Update available", msg + "\n\nOpen download page?", parent=self.top):
            webbrowser.open(info.download_url or PURCHASE_URL)
