"""Wishlist tab: toolbar, tree, and refresh logic."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import customtkinter as ctk
from tkinter import StringVar, ttk

from core.wishlist import load_wishlist, release_id_from_entry
from gui import constants as ui
from gui.tooltip import ToolTip

if TYPE_CHECKING:
  from autosort_gui import App


class WishlistPanel:
  """Builds the Wishlist tab; event handlers remain on App."""

  def __init__(self, app: App) -> None:
    self.app = app

  @property
  def _a(self):
    return self.app

  def build_tab(self, parent) -> None:
    a = self._a
    a._wishlist_tab = ctk.CTkFrame(parent, fg_color="transparent")
    a._wishlist_tab.rowconfigure(1, weight=1)
    a._wishlist_tab.columnconfigure(0, weight=1)

    toolbar_fr = ctk.CTkFrame(a._wishlist_tab, fg_color="transparent")
    toolbar_fr.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

    a._wishlist_check_btn = ctk.CTkButton(
      toolbar_fr,
      text="🔍 Check Availability",
      command=a._check_wishlist_availability,
      corner_radius=8,
      height=42,
      fg_color=a._colors["accent"],
      hover_color=a._colors["button_hover"],
      font=(ui.FONT_SEGOE_UI, ui.FONT_MD),
    )
    a._wishlist_check_btn.pack(side="left", padx=(0, 8))
    ToolTip(a._wishlist_check_btn, "Check Discogs Marketplace for available copies of wishlist items")

    a._wishlist_status_var = StringVar(value="")
    wishlist_status_lbl = ctk.CTkLabel(
      toolbar_fr,
      textvariable=a._wishlist_status_var,
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      text_color=a._colors["muted"],
    )
    wishlist_status_lbl.pack(side="left", padx=8)

    self._build_tree(a._wishlist_tab, ui, grid_row=1)
    self.setup_events()

  def _build_tree(self, wishlist_fr, ui, grid_row: int = 0) -> None:
    a = self._a
    wishlist_wrap = ctk.CTkFrame(
      wishlist_fr,
      corner_radius=12,
      fg_color=a._colors["panel"],
      border_width=2,
      border_color=a._colors.get("card_border", a._colors["border"]),
    )
    wishlist_wrap.grid(row=grid_row, column=0, sticky="nsew", padx=(12, 12), pady=(0, 12))
    wishlist_wrap.rowconfigure(0, weight=1)
    wishlist_wrap.columnconfigure(0, weight=1)

    wishlist_scroll = ttk.Scrollbar(wishlist_wrap, orient="vertical")
    wishlist_scroll.grid(row=0, column=1, sticky="ns", pady=3, padx=(0, 3))

    wishlist_columns = ("Artist", "Title", "For Sale", "Lowest Price")
    a.wishlist_tree = ttk.Treeview(
      wishlist_wrap,
      columns=wishlist_columns,
      show="tree headings",
      selectmode="browse",
      yscrollcommand=wishlist_scroll.set,
    )
    wishlist_scroll.config(command=a.wishlist_tree.yview)
    a.wishlist_tree.config(columns=wishlist_columns, show="tree headings")
    a.wishlist_tree.heading("#0", text="", anchor="center")
    a.wishlist_tree.column("#0", width=50, minwidth=50, stretch=False, anchor="center")
    a.wishlist_tree.heading("Artist", text="Artist", anchor="w")
    a.wishlist_tree.heading("Title", text="Title", anchor="w")
    a.wishlist_tree.heading("For Sale", text="For Sale", anchor="center")
    a.wishlist_tree.heading("Lowest Price", text="Lowest Price", anchor="e")
    a.wishlist_tree.column("Artist", width=180, minwidth=80, stretch=True, anchor="w")
    a.wishlist_tree.column("Title", width=220, minwidth=100, stretch=True, anchor="w")
    a.wishlist_tree.column("For Sale", width=80, minwidth=60, stretch=False, anchor="center")
    a.wishlist_tree.column("Lowest Price", width=100, minwidth=80, stretch=False, anchor="e")
    a.wishlist_tree.grid(row=0, column=0, sticky="nsew", padx=(3, 0), pady=3)
    a._wishlist_rows = []

    a._wishlist_empty_label = ctk.CTkLabel(
      wishlist_wrap,
      text="Add items to your Discogs wantlist to see them here",
      font=(ui.FONT_SEGOE_UI, ui.FONT_LG),
      text_color=a._colors["muted"],
      justify="center",
    )
    a._wishlist_empty_label.grid(row=0, column=0, sticky="nsew", padx=(3, 0), pady=3)
    a._wishlist_empty_label.grid_remove()

  @staticmethod
  def make_wishlist_row(entry: dict):
    release_id = release_id_from_entry(entry)
    return SimpleNamespace(
      artist_display=entry.get("artist", ""),
      title=entry.get("title", ""),
      year=entry.get("year", ""),
      label=entry.get("label", ""),
      catno=entry.get("catno", ""),
      country=entry.get("country", ""),
      format_str=entry.get("format", ""),
      discogs_url=entry.get("discogs_url", entry.get("url", "")),
      notes=entry.get("notes", ""),
      release_id=release_id,
      master_id=entry.get("master_id"),
      sort_artist=entry.get("artist", ""),
      sort_title=entry.get("title", ""),
      median_price=entry.get("median_price"),
      lowest_price=entry.get("lowest_price"),
      num_for_sale=entry.get("num_for_sale"),
      price_currency=entry.get("price_currency", ""),
      thumb_url=entry.get("thumb", ""),
      cover_image_url=entry.get("cover_image_url", ""),
      genres=entry.get("genres", ""),
      styles=entry.get("styles", ""),
      companies=entry.get("companies", ""),
      contributors=entry.get("contributors", ""),
      barcode=entry.get("barcode", ""),
      tracklist=entry.get("tracklist", ""),
      extra=entry.get("extra", ""),
    )

  def setup_events(self) -> None:
    a = self._a

    def refresh_wishlist_tree():
      a.wishlist_tree.delete(*a.wishlist_tree.get_children())
      a._wishlist_rows = []
      wishlist_data = list(load_wishlist())
      if not wishlist_data:
        if hasattr(a, "_wishlist_empty_label"):
          a._wishlist_empty_label.grid()
        return
      if hasattr(a, "_wishlist_empty_label"):
        a._wishlist_empty_label.grid_remove()
      for i, entry in enumerate(wishlist_data):
        row = self.make_wishlist_row(entry)
        a._wishlist_rows.append(row)
        placeholder = a._get_placeholder_image()
        img = a._get_row_image(row, placeholder)

        num_for_sale = getattr(row, "num_for_sale", None)
        lowest_price = getattr(row, "lowest_price", None)
        price_currency = getattr(row, "price_currency", "") or a.v_currency.get()

        if num_for_sale is not None and num_for_sale > 0:
          for_sale_text = f"✓ {num_for_sale}"
          price_text = f"{price_currency} {lowest_price:.2f}" if lowest_price is not None else "—"
        else:
          for_sale_text = "—"
          price_text = "—"

        values = (
          str(getattr(row, "artist_display", "")),
          str(getattr(row, "title", "")),
          for_sale_text,
          price_text,
        )

        if num_for_sale is not None and num_for_sale > 0:
          tag = "row_available" if i % 2 == 0 else "row_available_odd"
        else:
          tag = "row_odd" if i % 2 == 1 else "row_even"

        if img:
          a.wishlist_tree.insert("", "end", image=img, values=values, tags=(tag,))
        else:
          a.wishlist_tree.insert("", "end", values=values, tags=(tag,))

      a.wishlist_tree.tag_configure("row_available", background="#1e3a2f")
      a.wishlist_tree.tag_configure("row_available_odd", background="#163028")

      if hasattr(a, "_thumbnails_enabled") and a._thumbnails_enabled:
        a._download_missing_thumbnails(a._wishlist_rows)

    a.refresh_wishlist_tree = refresh_wishlist_tree
    a.refresh_wishlist_tree()
    a.wishlist_tree.bind("<Double-1>", a._on_wishlist_double_click)
    a.wishlist_tree.bind("<Button-3>", a._on_wishlist_right_click)
    a.wishlist_tree.bind("<Motion>", a._on_wishlist_tree_motion)
    a.wishlist_tree.bind("<Leave>", a._on_wishlist_tree_leave)
    a.wishlist_tree.bind("<Button-1>", a._on_wishlist_click)
