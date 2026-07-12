"""Pro license activation dialog."""

from __future__ import annotations

import tkinter as tk
import webbrowser

import customtkinter as ctk
from tkinter import messagebox

from core.licensing import activate_license, deactivate_license, is_pro, license_summary
from core.version import APP_NAME, PURCHASE_URL


class LicenseDialog:
    def __init__(self, parent, on_changed=None) -> None:
        self._on_changed = on_changed
        self.top = ctk.CTkToplevel(parent)
        self.top.title(f"{APP_NAME} — Pro License")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.geometry("480x320")
        self.top.resizable(False, False)

        body = ctk.CTkFrame(self.top, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(body, text="License status", font=("Segoe UI Semibold", 18)).pack(anchor="w")
        self._status = ctk.CTkLabel(body, text=license_summary(), font=("Segoe UI", 14))
        self._status.pack(anchor="w", pady=(8, 16))

        ctk.CTkLabel(body, text="Enter license key", anchor="w").pack(anchor="w")
        self._key = ctk.CTkEntry(body, width=400, placeholder_text="VSS1-…")
        self._key.pack(anchor="w", pady=(4, 12))

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="Activate", command=self._activate).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Buy Pro", command=lambda: webbrowser.open(PURCHASE_URL)).pack(side="left", padx=(0, 8))
        if is_pro():
            ctk.CTkButton(row, text="Deactivate", command=self._deactivate, fg_color="#4a5568").pack(side="left")
        ctk.CTkButton(row, text="Close", command=self.top.destroy).pack(side="right")

        ctk.CTkLabel(
            body,
            text="Pro: unlimited collection, prices, wishlist checks, manual order, audio previews.",
            wraplength=420,
            justify="left",
            text_color="#94a3b8",
            font=("Segoe UI", 12),
        ).pack(anchor="w", pady=(16, 0))

    def _activate(self) -> None:
        ok, msg = activate_license(self._key.get())
        if ok:
            messagebox.showinfo("Pro", msg, parent=self.top)
            self._status.configure(text=license_summary())
            if self._on_changed:
                self._on_changed()
        else:
            messagebox.showerror("License", msg, parent=self.top)

    def _deactivate(self) -> None:
        deactivate_license()
        self._status.configure(text=license_summary())
        if self._on_changed:
            self._on_changed()
