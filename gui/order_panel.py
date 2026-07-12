"""Shelf order tab: manual-order toolbar and collection Treeview."""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

from gui import constants as ui
from gui.thumbnails import ImagePreviewPopup

if TYPE_CHECKING:
  from autosort_gui import App


class OrderPanel:
  """Builds the Shelf Order tab; widgets and handlers remain on App."""

  def __init__(self, app: App) -> None:
    self.app = app

  @property
  def _a(self):
    return self.app

  def build_tab(self, parent) -> None:
    a = self._a
    a._order_tab = ctk.CTkFrame(parent, fg_color="transparent")
    a._order_tab.rowconfigure(1, weight=1)
    a._order_tab.columnconfigure(0, weight=1)
    self._build_toolbar(a._order_tab, ui)
    self._build_tree(a._order_tab, ui)

  def _build_toolbar(self, order_fr, ui) -> None:
    a = self._a
    order_toolbar = ctk.CTkFrame(order_fr, fg_color="transparent")
    order_toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
    a._manual_order_check = ctk.CTkCheckBox(
      order_toolbar,
      text="✋ Manual Order Mode",
      variable=a.v_manual_order_enabled,
      command=a._toggle_manual_order,
      corner_radius=6,
      font=(ui.FONT_SEGOE_UI, ui.FONT_MD),
      fg_color=a._colors["accent"],
      hover_color=a._colors["button_hover"],
    )
    a._manual_order_check.grid(row=0, column=0, sticky="w", padx=(0, 16))
    a._manual_order_hint = ctk.CTkLabel(
      order_toolbar,
      text="(Drag rows to reorder)",
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      text_color=a._colors["muted"],
    )
    a._manual_order_hint.grid(row=0, column=1, sticky="w", padx=(0, 16))
    a._reset_order_btn = ctk.CTkButton(
      order_toolbar,
      text="↺ Reset to Auto Sort",
      command=a._reset_manual_order,
      corner_radius=8,
      height=42,
      fg_color="#f59e0b",
      hover_color="#d97706",
      font=(ui.FONT_SEGOE_UI, ui.FONT_MD),
    )
    a._reset_order_btn.grid(row=0, column=2, sticky="e", padx=(0, 8))
    a._move_up_btn = ctk.CTkButton(
      order_toolbar,
      text="▲ Up",
      command=a._move_item_up,
      corner_radius=8,
      height=42,
      width=80,
      fg_color="#4a5568",
      hover_color="#2d3748",
      font=(ui.FONT_SEGOE_UI, ui.FONT_MD),
    )
    a._move_up_btn.grid(row=0, column=3, sticky="e", padx=(8, 4))
    a._move_down_btn = ctk.CTkButton(
      order_toolbar,
      text="▼ Down",
      command=a._move_item_down,
      corner_radius=8,
      height=42,
      width=80,
      fg_color="#4a5568",
      hover_color="#2d3748",
      font=(ui.FONT_SEGOE_UI, ui.FONT_MD),
    )
    a._move_down_btn.grid(row=0, column=4, sticky="e", padx=(0, 8))
    order_toolbar.columnconfigure(1, weight=1)

  def _build_tree(self, order_fr, ui) -> None:
    a = self._a
    order_wrap = ctk.CTkFrame(
      order_fr,
      corner_radius=12,
      fg_color=a._colors["panel"],
      border_width=2,
      border_color=a._colors.get("card_border", a._colors["border"]),
    )
    order_wrap.grid(row=1, column=0, sticky="nsew", padx=(12, 12), pady=(0, 12))
    order_wrap.rowconfigure(0, weight=1)
    order_wrap.columnconfigure(0, weight=1)
    order_scroll = ttk.Scrollbar(order_wrap, orient="vertical")
    order_scroll.grid(row=0, column=1, sticky="ns", pady=3, padx=(0, 3))
    columns = ("#", "Artist", "Title", "Year", "Label", "Price")
    tree_style = "Dark.Treeview" if a.v_dark_mode.get() else "Light.Treeview"
    a.order_tree = ttk.Treeview(
      order_wrap,
      columns=columns,
      show="tree headings",
      yscrollcommand=order_scroll.set,
      selectmode="browse",
      style=tree_style,
    )
    a.order_tree.grid(row=0, column=0, sticky="nsew", padx=(3, 0), pady=3)
    order_scroll.config(command=a.order_tree.yview)

    a._order_empty_label = ctk.CTkLabel(
      order_wrap,
      text="No albums yet. Sign in with Discogs and click Refresh to load your collection.",
      font=(ui.FONT_SEGOE_UI, ui.FONT_LG),
      text_color=a._colors["muted"],
      justify="center",
    )
    a._order_empty_label.grid(row=0, column=0, sticky="nsew", padx=(3, 0), pady=3)
    a._order_empty_label.grid_remove()

    a._order_loading_overlay = ctk.CTkFrame(order_wrap, fg_color=a._colors["panel"])
    a._order_loading_overlay.grid(row=0, column=0, sticky="nsew", padx=(3, 0), pady=3)
    a._order_loading_overlay.grid_rowconfigure(0, weight=1)
    a._order_loading_overlay.grid_rowconfigure(2, weight=1)
    a._order_loading_overlay.grid_columnconfigure(0, weight=1)

    loading_content = ctk.CTkFrame(a._order_loading_overlay, fg_color="transparent")
    loading_content.grid(row=1, column=0)

    from gui.spinning_record import SpinningRecord

    a._order_loading_spinner = SpinningRecord(
      loading_content,
      size=120,
      bg=a._colors["panel"],
      accent=a._colors["accent"],
    )
    a._order_loading_spinner.pack(pady=(0, 12))

    a._order_loading_label = ctk.CTkLabel(
      loading_content,
      text="Loading your collection…",
      font=(ui.FONT_SEGOE_UI, ui.FONT_LG),
      text_color=a._colors["muted"],
      justify="center",
    )
    a._order_loading_label.pack()

    a._order_loading_detail = ctk.CTkLabel(
      loading_content,
      text="Connecting to Discogs…",
      font=(ui.FONT_SEGOE_UI, ui.FONT_SM),
      text_color=a._colors["muted"],
      justify="center",
    )
    a._order_loading_detail.pack(pady=(8, 10))

    a._order_loading_progress = ctk.CTkProgressBar(
      loading_content,
      width=280,
      height=14,
      corner_radius=7,
      progress_color=a._colors["accent"],
      fg_color=a._colors.get("panel2", a._colors["border"]),
    )
    a._order_loading_progress.pack()
    a._order_loading_progress.set(0)
    a._order_loading_progress.start()

    if a._last_result is None:
      a._show_order_loading_state(True)
    else:
      a._show_order_loading_state(False)

    a.order_tree.heading("#0", text="", anchor="center")
    a.order_tree.column("#0", width=50, minwidth=50, stretch=False, anchor="center")
    a.order_tree.heading("#", text="#", anchor="center")
    a.order_tree.heading("Artist", text="Artist", anchor="w")
    a.order_tree.heading("Title", text="Title", anchor="w")
    a.order_tree.heading("Year", text="Year", anchor="center")
    a.order_tree.heading("Label", text="Label / Cat#", anchor="w")
    a.order_tree.heading("Price", text="Price", anchor="e")
    a.order_tree.column("#", width=35, minwidth=30, stretch=False, anchor="center")
    a.order_tree.column("Artist", width=200, minwidth=100, stretch=True, anchor="w")
    a.order_tree.column("Title", width=260, minwidth=120, stretch=True, anchor="w")
    a.order_tree.column("Year", width=50, minwidth=45, stretch=False, anchor="center")
    a.order_tree.column("Label", width=280, minwidth=100, stretch=True, anchor="w")
    a.order_tree.column("Price", width=80, minwidth=70, stretch=False, anchor="e")
    if not a.v_show_prices.get():
      a.order_tree.column("Price", width=0, minwidth=0, stretch=False)
    a.order_tree.tag_configure("row_even", background=a._colors["order_bg"], foreground=a._colors["order_fg"])
    a.order_tree.tag_configure(
      "row_odd",
      background="#1a2d4d" if a.v_dark_mode.get() else "#f0f4f8",
      foreground=a._colors["order_fg"],
    )
    a.order_tree.tag_configure("search_match", background="#fbbf24", foreground="#1a1a2e")
    a.order_tree.tag_configure("dragging", background=a._colors["accent"], foreground="#ffffff")
    a._configure_treeview_style()
    a.order_tree.bind("<ButtonPress-1>", a._on_drag_start)
    a.order_tree.bind("<B1-Motion>", a._on_drag_motion)
    a.order_tree.bind("<ButtonRelease-1>", a._on_drag_end)
    a.order_tree.bind("<Motion>", a._on_tree_motion)
    a.order_tree.bind("<Leave>", a._on_tree_leave)
    a.order_tree.bind("<Double-1>", a._on_album_double_click)
    a._image_preview = ImagePreviewPopup(a.root, a._thumbnail_cache)
    a._hover_release_id = None
    a.order_text = tk.Text(order_wrap, height=1, width=1)
    a._tree_rows = []
