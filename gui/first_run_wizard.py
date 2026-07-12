"""First-run onboarding wizard."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from core.config_store import load_config, save_config
from core.version import APP_NAME, DISCOGS_DISCLAIMER


class FirstRunWizard:
    """Modal wizard shown once after install."""

    def __init__(self, app) -> None:
        self.app = app
        self.completed = False

        self.top = ctk.CTkToplevel(app.root)
        self.top.title(f"Welcome to {APP_NAME}")
        self.top.transient(app.root)
        self.top.grab_set()
        self.top.geometry("520x400")
        self.top.resizable(False, False)

        self._step = 0
        self.body = ctk.CTkFrame(self.top, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=28, pady=24)
        self._render_step()

    def _render_step(self) -> None:
        for w in self.body.winfo_children():
            w.destroy()

        nav = ctk.CTkFrame(self.body, fg_color="transparent")
        nav.pack(side="bottom", fill="x", pady=(16, 0))

        if self._step == 0:
            ctk.CTkLabel(self.body, text=f"Welcome to {APP_NAME}", font=("Segoe UI Semibold", 22)).pack(anchor="w")
            ctk.CTkLabel(
                self.body,
                text=(
                    "Sort your Discogs vinyl collection for real-world shelves.\n\n"
                    f"{DISCOGS_DISCLAIMER}\n\n"
                    "Your collection data stays on this computer. See Privacy Policy in Help → About."
                ),
                justify="left",
                wraplength=460,
                font=("Segoe UI", 14),
            ).pack(anchor="w", pady=(12, 0))
            ctk.CTkButton(nav, text="Next", command=lambda: self._goto(1)).pack(side="right")
        elif self._step == 1:
            ctk.CTkLabel(self.body, text="Sign in with Discogs", font=("Segoe UI Semibold", 20)).pack(anchor="w")
            ctk.CTkLabel(
                self.body,
                text="Connect your account to load your collection. Your browser opens once to approve access.",
                wraplength=460,
                justify="left",
            ).pack(anchor="w", pady=(12, 16))
            ctk.CTkButton(nav, text="Back", command=lambda: self._goto(0)).pack(side="left")
            ctk.CTkButton(nav, text="Sign in", command=self._signin).pack(side="right", padx=(8, 0))
            ctk.CTkButton(nav, text="Skip for now", command=lambda: self._goto(2)).pack(side="right")
        elif self._step == 2:
            ctk.CTkLabel(self.body, text="Output folder", font=("Segoe UI Semibold", 20)).pack(anchor="w")
            ctk.CTkLabel(
                self.body,
                text="Exported shelf lists (TXT, CSV) are saved here.",
                wraplength=460,
                justify="left",
            ).pack(anchor="w", pady=(12, 8))
            row = ctk.CTkFrame(self.body, fg_color="transparent")
            row.pack(fill="x", pady=(0, 12))
            ctk.CTkEntry(row, textvariable=self.app.v_output_dir, width=320).pack(side="left", padx=(0, 8))
            ctk.CTkButton(row, text="Browse…", command=self._browse).pack(side="left")
            ctk.CTkButton(nav, text="Back", command=lambda: self._goto(1)).pack(side="left")
            ctk.CTkButton(nav, text="Next", command=lambda: self._goto(3)).pack(side="right")
        else:
            ctk.CTkLabel(self.body, text="Marketplace prices (optional)", font=("Segoe UI Semibold", 20)).pack(anchor="w")
            ctk.CTkLabel(
                self.body,
                text=(
                    "Pro unlocks marketplace prices, wishlist checks, and unlimited collection size.\n\n"
                    "You can enable prices later in Settings. First load may take several minutes for large collections."
                ),
                wraplength=460,
                justify="left",
            ).pack(anchor="w", pady=(12, 16))
            from core.feature_gate import can_fetch_prices

            if can_fetch_prices():
                ctk.CTkCheckBox(self.body, text="Show marketplace prices", variable=self.app.v_show_prices).pack(anchor="w")
            else:
                ctk.CTkLabel(self.body, text="Upgrade to Pro in Settings to enable prices.", text_color="#94a3b8").pack(anchor="w")
            ctk.CTkButton(nav, text="Back", command=lambda: self._goto(2)).pack(side="left")
            ctk.CTkButton(nav, text="Finish", command=self._finish).pack(side="right")

    def _goto(self, step: int) -> None:
        self._step = step
        self._render_step()

    def _signin(self) -> None:
        self.app._do_oauth_signin()
        self._goto(2)

    def _browse(self) -> None:
        d = filedialog.askdirectory(initialdir=self.app.v_output_dir.get())
        if d:
            self.app.v_output_dir.set(d)

    def _finish(self) -> None:
        cfg = load_config()
        cfg["wizard_completed"] = True
        save_config(cfg)
        self.app._save_settings()
        self.completed = True
        self.top.destroy()

    def run(self) -> None:
        self.app.root.wait_window(self.top)
