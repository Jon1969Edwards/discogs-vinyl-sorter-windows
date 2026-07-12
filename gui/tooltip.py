"""Hover tooltips for GUI widgets."""

from __future__ import annotations

import tkinter as tk

from gui.constants import FONT_SEGOE_UI, FONT_XS


class ToolTip:
  """Modern tooltip that appears on hover with a slight delay."""

  EVENT_LEAVE = "<Leave>"

  def __init__(self, widget, text: str, delay: int = 400, wraplength: int = 280):
    self.widget = widget
    self.text = text
    self.delay = delay
    self.wraplength = wraplength
    self.tip_window = None
    self.id_after = None

    widget.bind("<Enter>", self._on_enter)
    widget.bind(self.EVENT_LEAVE, self._on_leave)
    widget.bind("<ButtonPress>", self._on_leave)

  def _on_enter(self, event=None):
    self._cancel()
    self.id_after = self.widget.after(self.delay, self._show_tip)

  def _on_leave(self, event=None):
    self._cancel()
    self._hide_tip()

  def _cancel(self):
    if self.id_after:
      self.widget.after_cancel(self.id_after)
      self.id_after = None

  def _show_tip(self):
    if self.tip_window:
      return

    x = self.widget.winfo_rootx() + 20
    y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

    self.tip_window = tw = tk.Toplevel(self.widget)
    tw.wm_overrideredirect(True)
    tw.wm_geometry(f"+{x}+{y}")
    tw.configure(bg="#1a1a2e")

    frame = tk.Frame(tw, bg="#1a1a2e", bd=1, relief="solid", highlightbackground="#6c63ff", highlightthickness=1)
    frame.pack()

    label = tk.Label(
      frame,
      text=self.text,
      justify="left",
      background="#1a1a2e",
      foreground="#eaeaea",
      font=(FONT_SEGOE_UI, FONT_XS),
      wraplength=self.wraplength,
      padx=10,
      pady=6,
    )
    label.pack()

  def _hide_tip(self):
    if self.tip_window:
      self.tip_window.destroy()
      self.tip_window = None

  def update_text(self, new_text: str):
    """Update tooltip text dynamically."""
    self.text = new_text
