"""Pro license activation dialog."""

from __future__ import annotations

import webbrowser

import customtkinter as ctk
from tkinter import messagebox

from core.licensing import activate_license, deactivate_license, is_pro, license_summary
from core.version import APP_NAME, PURCHASE_URL, purchase_store_ready


_PRO_BENEFITS = (
    "Unlimited collection size (no 100-record Free limit)",
    "Marketplace prices with local cache",
    "Wishlist availability checks",
    "Manual shelf order and audio previews",
)


class LicenseDialog:
    def __init__(self, parent, on_changed=None) -> None:
        self._on_changed = on_changed
        self.top = ctk.CTkToplevel(parent)
        self.top.title(f"{APP_NAME} — Pro")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.geometry("500x420")
        self.top.resizable(False, False)

        body = ctk.CTkFrame(self.top, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(body, text="Pro license", font=("Segoe UI Semibold", 20)).pack(anchor="w")
        self._status = ctk.CTkLabel(
            body,
            text=f"Status: {license_summary()}",
            font=("Segoe UI", 14),
            text_color="#94a3b8",
        )
        self._status.pack(anchor="w", pady=(6, 12))

        ctk.CTkLabel(body, text="Included with Pro:", font=("Segoe UI Semibold", 13)).pack(anchor="w")
        for line in _PRO_BENEFITS:
            ctk.CTkLabel(
                body,
                text=f"•  {line}",
                font=("Segoe UI", 12),
                text_color="#cbd5e1",
                anchor="w",
            ).pack(anchor="w", pady=1)

        if is_pro():
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=(20, 0))
            ctk.CTkButton(
                row,
                text="Deactivate",
                command=self._deactivate,
                fg_color="#4a5568",
                hover_color="#2d3748",
                width=120,
            ).pack(side="left")
            ctk.CTkButton(row, text="Close", command=self.top.destroy).pack(side="right")
            return

        ctk.CTkLabel(body, text="Already have a key?", font=("Segoe UI Semibold", 13)).pack(
            anchor="w", pady=(16, 4)
        )
        self._key = ctk.CTkEntry(
            body,
            width=440,
            placeholder_text="Paste your Pro key (starts with VSS1-)",
        )
        self._key.pack(anchor="w", pady=(0, 12))

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="Activate", command=self._activate, width=120).pack(
            side="left", padx=(0, 8)
        )
        if purchase_store_ready():
            ctk.CTkButton(
                row,
                text="Buy Pro",
                command=lambda: webbrowser.open(PURCHASE_URL),
                width=100,
                fg_color="#f59e0b",
                hover_color="#d97706",
            ).pack(side="left", padx=(0, 8))
        else:
            ctk.CTkLabel(
                row,
                text="Purchase coming soon",
                font=("Segoe UI", 12),
                text_color="#64748b",
            ).pack(side="left", padx=(4, 0))
        ctk.CTkButton(row, text="Close", command=self.top.destroy).pack(side="right")

    def _activate(self) -> None:
        ok, msg = activate_license(self._key.get())
        if ok:
            if self._on_changed:
                self._on_changed()
            messagebox.showinfo(
                "Pro unlocked",
                "Pro is active. Unlimited collection, prices, and other Pro tools are available.",
                parent=self.top,
            )
            self.top.destroy()
        else:
            messagebox.showerror("License", msg, parent=self.top)

    def _deactivate(self) -> None:
        if not messagebox.askyesno(
            "Deactivate Pro",
            "Remove Pro from this computer? Free limits will apply again.",
            parent=self.top,
        ):
            return
        deactivate_license()
        self._status.configure(text=f"Status: {license_summary()}")
        if self._on_changed:
            self._on_changed()
        self.top.destroy()
