"""Animated vinyl record spinner for loading states."""

from __future__ import annotations

import math
import tkinter as tk


class SpinningRecord:
  """Canvas widget that draws a spinning vinyl record."""

  def __init__(
    self,
    parent,
    *,
    size: int = 100,
    bg: str = "#16213e",
    accent: str = "#6c63ff",
  ) -> None:
    self.canvas = tk.Canvas(
      parent,
      width=size,
      height=size,
      bg=bg,
      highlightthickness=0,
    )
    self._size = size
    self._cx = size // 2
    self._cy = size // 2
    self._bg = bg
    self._accent = accent
    self.angle = 0
    self.spinning = False
    self._after_id: str | None = None

  def pack(self, **kwargs) -> None:
    self.canvas.pack(**kwargs)

  def grid(self, **kwargs) -> None:
    self.canvas.grid(**kwargs)

  def start(self) -> None:
    if self.spinning:
      return
    self.spinning = True
    self._animate()

  def stop(self) -> None:
    self.spinning = False
    if self._after_id is not None:
      try:
        self.canvas.after_cancel(self._after_id)
      except Exception:
        pass
      self._after_id = None

  def set_colors(self, *, bg: str | None = None, accent: str | None = None) -> None:
    if bg is not None:
      self._bg = bg
      self.canvas.configure(bg=bg)
    if accent is not None:
      self._accent = accent
    if self.spinning:
      self._draw_record()

  def _draw_record(self) -> None:
    cx, cy = self._cx, self._cy
    scale = self._size / 100.0
    self.canvas.delete("all")

    pad = 2 * scale
    outer = self._size - pad
    self.canvas.create_oval(pad, pad + 1, outer, outer + 1, fill="#151525", outline="")
    self.canvas.create_oval(pad, pad, outer, outer, fill="#2a2a3e", outline="#3a3a4e", width=max(1, int(2 * scale)))
    self.canvas.create_oval(5 * scale, 5 * scale, 95 * scale, 95 * scale, fill="#1a1a1a", outline="#0a0a0a", width=1)

    for r in range(int(42 * scale), int(15 * scale), -int(4 * scale) or -1):
      self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#252525", width=1)

    label_r = 12 * scale
    self.canvas.create_oval(
      cx - label_r, cy - label_r, cx + label_r, cy + label_r,
      fill=self._accent, outline="#5a52dd", width=max(1, int(2 * scale)),
    )
    spindle_r = 3 * scale
    self.canvas.create_oval(
      cx - spindle_r, cy - spindle_r, cx + spindle_r, cy + spindle_r,
      fill="#1a1a2e", outline="#0a0a1e", width=1,
    )

    for offset, color, width in (
      (0, "#ffffff", max(2, int(3 * scale))),
      (120, "#888888", max(1, int(2 * scale))),
      (240, "#444444", max(1, int(1 * scale))),
    ):
      angle_rad = math.radians(self.angle + offset)
      x1 = cx + 14 * scale * math.cos(angle_rad)
      y1 = cy + 14 * scale * math.sin(angle_rad)
      x2 = cx + 42 * scale * math.cos(angle_rad)
      y2 = cy + 42 * scale * math.sin(angle_rad)
      self.canvas.create_line(x1, y1, x2, y2, fill=color, width=width, capstyle="round")

  def _animate(self) -> None:
    if not self.spinning:
      return
    self.angle = (self.angle + 10) % 360
    self._draw_record()
    try:
      self._after_id = self.canvas.after(40, self._animate)
    except Exception:
      self._after_id = None
