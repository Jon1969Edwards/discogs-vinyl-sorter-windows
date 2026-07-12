"""One-time developer dialog to bundle Discogs OAuth credentials."""

from __future__ import annotations

import webbrowser
from typing import Optional, Tuple

import customtkinter as ctk
from tkinter import messagebox

from core.oauth_discogs import save_consumer_credentials

DEVELOPERS_URL = "https://www.discogs.com/settings/developers"
CALLBACK_URL = "http://127.0.0.1:8765/callback"


class OAuthSetupDialog:
  """Collect Discogs app credentials once so end users can sign in with one click."""

  def __init__(self, parent) -> None:
    self.result: Optional[Tuple[str, str]] = None

    self.top = ctk.CTkToplevel(parent)
    self.top.title("One-time app setup")
    self.top.transient(parent)
    self.top.grab_set()
    self.top.geometry("560x400")
    self.top.resizable(False, False)

    body = ctk.CTkFrame(self.top, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=24, pady=20)
    body.columnconfigure(0, weight=1)

    ctk.CTkLabel(
      body,
      text="Enable Sign in with Discogs",
      font=("Segoe UI Semibold", 20),
    ).grid(row=0, column=0, sticky="w", pady=(0, 8))

    ctk.CTkLabel(
      body,
      text=(
        "This one-time step is for whoever installs or distributes the app.\n"
        "After saving, users only click \"Sign in with Discogs\" — no tokens to copy.\n\n"
        f"Callback URL when creating the Discogs app: {CALLBACK_URL}"
      ),
      justify="left",
      wraplength=500,
      font=("Segoe UI", 13),
      text_color="#94a3b8",
    ).grid(row=1, column=0, sticky="w", pady=(0, 12))

    ctk.CTkButton(
      body,
      text="Open Discogs Developers",
      width=200,
      command=lambda: webbrowser.open(DEVELOPERS_URL),
    ).grid(row=2, column=0, sticky="w", pady=(0, 16))

    ctk.CTkLabel(body, text="Consumer Key", anchor="w", font=("Segoe UI", 13)).grid(
      row=3, column=0, sticky="ew", pady=(0, 4)
    )
    self.key_entry = ctk.CTkEntry(body, width=480, height=36)
    self.key_entry.grid(row=4, column=0, sticky="ew", pady=(0, 12))

    ctk.CTkLabel(body, text="Consumer Secret", anchor="w", font=("Segoe UI", 13)).grid(
      row=5, column=0, sticky="ew", pady=(0, 4)
    )
    self.secret_entry = ctk.CTkEntry(body, width=480, height=36, show="•")
    self.secret_entry.grid(row=6, column=0, sticky="ew", pady=(0, 16))

    btn_row = ctk.CTkFrame(body, fg_color="transparent")
    btn_row.grid(row=7, column=0, sticky="e")

    ctk.CTkButton(
      btn_row,
      text="Cancel",
      width=90,
      fg_color="#4a5568",
      hover_color="#2d3748",
      command=self._cancel,
    ).pack(side="left", padx=(0, 8))

    ctk.CTkButton(
      btn_row,
      text="Save & continue",
      width=140,
      command=self._save,
    ).pack(side="left")

    self.top.protocol("WM_DELETE_WINDOW", self._cancel)
    self.top.bind("<Return>", lambda _e: self._save())
    self.top.bind("<Escape>", lambda _e: self._cancel())
    self.key_entry.focus_set()

    parent.wait_window(self.top)

  def _cancel(self) -> None:
    self.result = None
    self.top.grab_release()
    self.top.destroy()

  def _save(self) -> None:
    key = self.key_entry.get().strip()
    secret = self.secret_entry.get().strip()
    if not key or not secret:
      messagebox.showerror("Missing credentials", "Enter both the Consumer Key and Consumer Secret.")
      return
    try:
      save_consumer_credentials(key, secret)
    except Exception as e:
      messagebox.showerror("Save failed", str(e))
      return
    self.result = (key, secret)
    self.top.grab_release()
    self.top.destroy()
