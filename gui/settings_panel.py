"""Settings sidebar for Discogs Auto-Sort (scrollable panel + format checkboxes)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from core.format_filter import FORMAT_FILTERS
from gui import constants as ui
from gui.tooltip import ToolTip

if TYPE_CHECKING:
  from autosort_gui import App


class SettingsPanel:
  """Builds the left settings sidebar; widgets are attached on the App for compatibility."""

  def __init__(self, app: App) -> None:
    self.app = app

  @property
  def _a(self):
    return self.app

  def build(self, frm, row: int) -> None:
    """Create settings frame, scroll area, and all section cards."""
    a = self._a
    a._settings_collapsed = True

    a._settings_frame = ctk.CTkFrame(
      frm,
      corner_radius=12,
      fg_color=a._colors["panel"],
      border_width=2,
      border_color=a._colors.get("card_border", a._colors["border"]),
    )
    a._settings_frame.grid(row=row, column=0, sticky="nsew", padx=(20, 10), pady=(16, 12))
    a._settings_frame.columnconfigure(0, weight=1)

    settings_header = ctk.CTkFrame(a._settings_frame, fg_color="transparent")
    settings_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 4))
    settings_header.columnconfigure(0, weight=1)

    ctk.CTkLabel(
      settings_header,
      text="⚙️ Settings",
      font=(ui.FONT_SEGOE_UI_SEMIBOLD, ui.FONT_XL),
      text_color=a._colors["text"],
    ).grid(row=0, column=0, sticky="w")

    a._settings_collapse_btn = ctk.CTkButton(
      settings_header,
      text="◀",
      width=36,
      height=32,
      corner_radius=6,
      fg_color=a._colors["accent"],
      hover_color=a._colors["button_hover"],
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      command=a._toggle_settings_sidebar,
    )
    a._settings_collapse_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))
    ToolTip(a._settings_collapse_btn, "Hide settings panel")

    a._settings_frame.rowconfigure(1, weight=1)
    a._settings_scroll = ctk.CTkScrollableFrame(
      a._settings_frame,
      fg_color="transparent",
      width=420,
    )
    a._settings_scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=(0, 8))
    a._settings_scroll.columnconfigure(0, weight=1)
    self._build_content(a._settings_scroll)

    a._settings_expand_tab = ctk.CTkFrame(
      frm,
      width=28,
      fg_color=a._colors["panel"],
      border_width=1,
      border_color=a._colors.get("card_border", a._colors["border"]),
      corner_radius=8,
    )
    a._settings_expand_tab.pack_propagate(False)
    a._settings_expand_btn = ctk.CTkButton(
      a._settings_expand_tab,
      text="⚙️ ▶",
      width=26,
      height=80,
      corner_radius=6,
      fg_color=a._colors["accent"],
      hover_color=a._colors["button_hover"],
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      command=a._toggle_settings_sidebar,
    )
    a._settings_expand_btn.pack(expand=True, fill="y", padx=2, pady=8)
    ToolTip(a._settings_expand_btn, "Show settings panel")
    a._settings_row = row

    if a._settings_collapsed:
      a._settings_frame.grid_remove()
      a._settings_expand_tab.grid(row=row, column=0, sticky="ns", padx=(20, 10), pady=(16, 12))
      a._settings_collapse_btn.configure(text="▶")

  def _build_content(self, settings) -> None:
    import tkinter as tk

    a = self._a
    settings.columnconfigure(0, weight=1)
    SECTION_PADX = 20
    SECTION_PADY = 16
    ITEM_SPACING = 10
    _section_row = [0]

    def make_entry(parent, textvar, width=200, show=""):
      return ctk.CTkEntry(
        parent,
        textvariable=textvar,
        width=width,
        height=38,
        show=show,
        font=(ui.FONT_SEGOE_UI, ui.FONT_MD),
        corner_radius=8,
      )

    def make_section(title, icon=""):
      section = ctk.CTkFrame(
        settings,
        fg_color=a._colors.get("panel2", a._colors["panel"]),
        corner_radius=10,
        border_width=1,
        border_color=a._colors.get("border", "#334155"),
      )
      section.grid(row=_section_row[0], column=0, sticky="ew", padx=SECTION_PADX, pady=(0, SECTION_PADY))
      _section_row[0] += 1
      section.columnconfigure(0, weight=1)
      if not hasattr(a, "_settings_section_frames"):
        a._settings_section_frames = []
      a._settings_section_frames.append(section)
      ctk.CTkLabel(
        section,
        text=f"{icon}  {title}" if icon else title,
        font=(ui.FONT_SEGOE_UI_SEMIBOLD, ui.FONT_LG),
        text_color=a._colors["accent"],
      ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))
      return section

    auth_section = make_section("Authentication", "🔐")
    ctk.CTkLabel(
      auth_section,
      text="Sign in with your Discogs account. Your browser opens once to approve access.",
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      text_color=a._colors["muted"],
      wraplength=360,
      justify="left",
    ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

    auth_btns = ctk.CTkFrame(auth_section, fg_color="transparent")
    auth_btns.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 8))
    a._signin_btn = ctk.CTkButton(
      auth_btns,
      text="🔐 Sign in with Discogs",
      command=a._do_oauth_signin,
      width=220,
      height=42,
      corner_radius=8,
      fg_color=a._colors["accent"],
      hover_color=a._colors["button_hover"],
      font=(ui.FONT_SEGOE_UI_SEMIBOLD, ui.FONT_MD),
    )
    a._signin_btn.pack(side="left", padx=(0, 8))
    ToolTip(
      a._signin_btn,
      "Opens Discogs in your browser. Click Approve — no password or token to copy.",
    )
    a._signout_btn = ctk.CTkButton(
      auth_btns,
      text="Sign out",
      command=a._do_oauth_signout,
      width=80,
      height=42,
      corner_radius=8,
      fg_color="#4a5568",
      hover_color="#2d3748",
    )
    a._signout_btn.pack(side="left")
    ToolTip(a._signout_btn, "Sign out of Discogs on this computer")
    a._auth_status_label = ctk.CTkLabel(
      auth_section,
      text="Not signed in",
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      text_color=a._colors["muted"],
    )
    a._auth_status_label.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 14))
    a._update_auth_buttons_state()

    output_section = make_section("Output Settings", "📁")
    ctk.CTkLabel(
      output_section,
      text="Output directory",
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      text_color=a._colors["muted"],
    ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 4))
    a._out_row = ctk.CTkFrame(output_section, fg_color="transparent")
    a._out_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, ITEM_SPACING))
    a._out_row.columnconfigure(0, weight=1)
    a._output_entry = make_entry(a._out_row, a.v_output_dir, width=200)
    a._output_entry.grid(row=0, column=0, sticky="ew")
    a._browse_btn = ctk.CTkButton(
      a._out_row,
      text="📂 Browse",
      command=a._choose_dir,
      width=100,
      corner_radius=8,
      height=38,
      fg_color=a._colors["accent"],
      hover_color=a._colors["button_hover"],
    )
    a._browse_btn.grid(row=0, column=1, sticky="e", padx=(12, 0))
    a._open_btn = None

    ctk.CTkLabel(
      output_section,
      text="Auto-refresh interval (seconds)",
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      text_color=a._colors["muted"],
    ).grid(row=3, column=0, sticky="w", padx=16, pady=(8, 4))
    poll_row = ctk.CTkFrame(output_section, fg_color="transparent")
    poll_row.grid(row=4, column=0, sticky="w", padx=16, pady=(0, ITEM_SPACING))
    a._poll_spin = tk.Spinbox(
      poll_row,
      from_=15,
      to=3600,
      textvariable=a.v_poll,
      width=8,
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      bg=a._colors["order_bg"],
      fg=a._colors["order_fg"],
      buttonbackground=a._colors["border"],
      insertbackground=a._colors["order_fg"],
      relief="solid",
      bd=1,
      highlightthickness=1,
      highlightbackground=a._colors["border"],
      highlightcolor=a._colors["accent"],
    )
    a._poll_spin.grid(row=0, column=0, ipady=4, ipadx=6)
    ctk.CTkLabel(
      output_section,
      text="How often to check Discogs for collection updates",
      font=(ui.FONT_SEGOE_UI, ui.FONT_XS),
      text_color=a._colors["muted"],
    ).grid(row=5, column=0, sticky="w", padx=16, pady=(0, 4))

    a._json_check = ctk.CTkCheckBox(
      output_section,
      text="Also export JSON files",
      variable=a.v_json,
      corner_radius=6,
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
    )
    a._json_check.grid(row=6, column=0, sticky="w", padx=16, pady=(8, 4))

    ctk.CTkLabel(
      output_section,
      text="TXT shelf dividers",
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      text_color=a._colors["muted"],
    ).grid(row=7, column=0, sticky="w", padx=16, pady=(8, 4))
    divider_row = ctk.CTkFrame(output_section, fg_color="transparent")
    divider_row.grid(row=8, column=0, sticky="w", padx=16, pady=(0, 4))
    a._divider_mode_combo = ctk.CTkOptionMenu(
      divider_row,
      variable=a.v_divider_mode,
      values=list(ui.DIVIDER_MODE_BY_LABEL.keys()),
      width=220,
      corner_radius=8,
    )
    a._divider_mode_combo.grid(row=0, column=0, sticky="w")
    ToolTip(
      a._divider_mode_combo,
      "Insert divider lines in exported/printed TXT. "
      "By shelf: A (A–H), B (I–P), C (Q–Z) for physical shelf units.",
    )
    ctk.CTkLabel(
      output_section,
      text="Shelf A: A–H  •  Shelf B: I–P  •  Shelf C: Q–Z (non-alpha → A)",
      font=(ui.FONT_SEGOE_UI, ui.FONT_XS),
      text_color=a._colors["muted"],
      justify="left",
    ).grid(row=9, column=0, sticky="w", padx=16, pady=(0, 14))

    price_section = make_section("Price Settings", "💰")
    a._prices_check = ctk.CTkCheckBox(
      price_section,
      text="Show prices in shelf order",
      variable=a.v_show_prices,
      corner_radius=6,
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
    )
    a._prices_check.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))

    ctk.CTkLabel(
      price_section,
      text="Currency",
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      text_color=a._colors["muted"],
    ).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 4))
    price_row = ctk.CTkFrame(price_section, fg_color="transparent")
    price_row.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
    price_row.columnconfigure(0, weight=1)
    a._currency_combo = ctk.CTkOptionMenu(
      price_row,
      variable=a.v_currency,
      values=["USD", "EUR", "GBP", "SEK", "CAD", "AUD", "JPY"],
      width=100,
      corner_radius=8,
    )
    a._currency_combo.grid(row=0, column=0, sticky="w")
    a._refresh_prices_btn = ctk.CTkButton(
      price_row,
      text="🔄 Refresh Prices",
      command=a._refresh_prices,
      corner_radius=8,
      height=38,
      fg_color=a._colors["accent"],
      hover_color=a._colors["button_hover"],
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
    )
    a._refresh_prices_btn.grid(row=0, column=1, sticky="w", padx=(12, 0))

    ctk.CTkLabel(
      price_section,
      text="Prices show lowest listed for your specific pressing",
      font=(ui.FONT_SEGOE_UI, ui.FONT_XS),
      text_color=a._colors["muted"],
      justify="left",
    ).grid(row=4, column=0, sticky="w", padx=16, pady=(4, 14))

    sort_section = make_section("Sorting", "🔤")
    ctk.CTkLabel(
      sort_section,
      text="Default sort order",
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      text_color=a._colors["muted"],
    ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 4))
    a._sort_row = ctk.CTkFrame(sort_section, fg_color="transparent")
    a._sort_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
    self._build_sort_content(a._sort_row)

    formats_section = make_section("Formats", "💿")
    ctk.CTkLabel(
      formats_section,
      text="Show these formats in your collection",
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      text_color=a._colors["muted"],
    ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 4))
    formats_row = ctk.CTkFrame(formats_section, fg_color="transparent")
    formats_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
    a._format_checks = {}
    for i, (key, label) in enumerate(FORMAT_FILTERS):
      chk = ctk.CTkCheckBox(
        formats_row,
        text=label,
        variable=a.v_formats[key],
        corner_radius=6,
        font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      )
      chk.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 16), pady=4)
      a._format_checks[key] = chk
    ToolTip(
      a._format_checks["everything"],
      "Show every item regardless of format (overrides the other checkboxes).",
    )
    self.update_format_checks_state()

  def _build_sort_content(self, sort_row) -> None:
    a = self._a
    sort_row.columnconfigure(0, weight=1)
    a._sort_combo = ctk.CTkOptionMenu(
      sort_row,
      variable=a.v_sort_by,
      values=["artist", "title", "year", "price_asc", "price_desc"],
      width=160,
      corner_radius=8,
      fg_color=a._colors.get("panel2", a._colors["panel"]),
      button_color=a._colors["accent"],
      button_hover_color=a._colors["button_hover"],
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
    )
    a._sort_combo.grid(row=0, column=0, sticky="ew")

  def update_format_checks_state(self) -> None:
    """Disable non-Everything format checkboxes while Everything is selected."""
    a = self._a
    if not hasattr(a, "_format_checks"):
      return
    everything_on = a.v_formats["everything"].get()
    for key, chk in a._format_checks.items():
      if key == "everything":
        continue
      chk.configure(state="disabled" if everything_on else "normal")

  def update_section_theme(self) -> None:
    """Recolor settings section cards after theme toggle."""
    a = self._a
    try:
      if hasattr(a, "_settings_section_frames"):
        panel2 = a._colors.get("panel2", a._colors["panel"])
        border = a._colors.get("border", "#334155")
        for section in a._settings_section_frames:
          try:
            section.configure(fg_color=panel2, border_color=border)
          except Exception:
            pass
    except Exception:
      pass
