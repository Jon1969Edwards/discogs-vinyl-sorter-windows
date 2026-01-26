#!/usr/bin/env python3
"""
Minimal Tkinter GUI wrapper for Discogs 33⅓ LP Shelf Sorter.

This GUI calls the existing functions in discogs_app.py and preserves the
CLI behavior. No additional dependencies beyond the Python stdlib.

How to run (macOS example):
  # optionally activate venv first
  # source ./.venv/bin/activate
  python gui_app.py
"""
from __future__ import annotations

import os
import sys
import queue
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from tkinter import Tk, StringVar, BooleanVar, IntVar, ttk, filedialog, messagebox

import webbrowser
import subprocess

# Local import of the core CLI module
import discogs_app as core
from core.models import ReleaseRow


@dataclass
class RunConfig:
  token: str
  user_agent: str
  output_dir: str
  per_page: int
  max_pages: int | None
  various_policy: str
  articles_extra: str
  lp_strict: bool
  debug_stats: bool
  last_name_first: bool
  lnf_allow_3: bool
  lnf_exclude: str
  lnf_safe_bands: bool
  dividers: bool
  txt_align: bool
  show_country: bool
  write_json: bool
  include_45s: bool
  include_cds: bool


class App:
  CLEAN_OUTPUTS_LABEL = "Clean Outputs"

  def __init__(self, root: Tk) -> None:
    self.root = root
    root.title("Discogs LP Shelf Sorter – GUI")

    # Dark/Light mode toggle
    self.v_dark_mode = BooleanVar(value=False)

    # Theme color palettes
    self._dark_colors = {
      "bg": "#0f172a",        # slate-900
      "panel": "#111827",     # gray-900
      "text": "#e5e7eb",      # gray-200
      "log_bg": "#0b1220",    # darker
      "log_fg": "#e5e7eb",    # gray-200
    }
    self._light_colors = {
      "bg": "#f8fafc",        # slate-50
      "panel": "#ffffff",     # white
      "text": "#1e293b",      # slate-800
      "log_bg": "#ffffff",    # white
      "log_fg": "#0f172a",    # slate-900
    }
    self._colors = self._light_colors.copy()

    # State vars
    self.v_token = StringVar(value="")
    self.v_user_agent = StringVar(value="VinylSorter/1.0 (+contact)")
    self.v_output_dir = StringVar(value=str(Path.cwd()))
    self.v_per_page = IntVar(value=100)
    self.v_max_pages = StringVar(value="")  # blank means None
    self.v_various = StringVar(value="normal")
    self.v_articles = StringVar(value="")
    self.v_lpf_strict = BooleanVar(value=False)
    self.v_debug = BooleanVar(value=False)
    self.v_lnf = BooleanVar(value=False)
    self.v_lnf_allow3 = BooleanVar(value=False)
    self.v_lnf_exclude = StringVar(value="")
    self.v_lnf_safe_bands = BooleanVar(value=True)
    self.v_dividers = BooleanVar(value=False)
    self.v_align = BooleanVar(value=False)
    self.v_country = BooleanVar(value=False)
    self.v_json = BooleanVar(value=False)
    self.v_inc_45s = BooleanVar(value=False)
    self.v_inc_cds = BooleanVar(value=False)

    self.log_q: queue.Queue[str] = queue.Queue()
    self.out_q: queue.Queue[str] = queue.Queue()

    self._build_ui(root)
    self._pump_logs()

  def _build_ui(self, root: Tk) -> None:
    pad = {"padx": 6, "pady": 4}

    frm = ttk.Frame(root)
    frm.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    # Token / UA / Output
    row = 0
    ttk.Label(frm, text="Token (optional)").grid(row=row, column=0, sticky="w", **pad)
    ttk.Entry(frm, textvariable=self.v_token, width=44).grid(row=row, column=1, sticky="ew", **pad)
    row += 1
    ttk.Label(frm, text="User-Agent").grid(row=row, column=0, sticky="w", **pad)
    ttk.Entry(frm, textvariable=self.v_user_agent, width=44).grid(row=row, column=1, sticky="ew", **pad)
    row += 1

    out_row = ttk.Frame(frm)
    out_row.grid(row=row, column=0, columnspan=2, sticky="ew", **pad)
    out_row.columnconfigure(1, weight=1)
    ttk.Label(out_row, text="Output Dir").grid(row=0, column=0, sticky="w")
    ttk.Entry(out_row, textvariable=self.v_output_dir).grid(row=0, column=1, sticky="ew", padx=4)
    ttk.Button(out_row, text="Browse", command=self._choose_dir).grid(row=0, column=2, sticky="e")
    row += 1

    # Options
    opt1 = ttk.LabelFrame(frm, text="Options")
    opt1.grid(row=row, column=0, columnspan=2, sticky="ew", **pad)
    row += 1

    # Row A: per-page, max-pages, various
    row_a = ttk.Frame(opt1)
    row_a.grid(row=0, column=0, sticky="ew", padx=4, pady=2)
    ttk.Label(row_a, text="Per-page").grid(row=0, column=0, sticky="w")
    ttk.Spinbox(row_a, from_=1, to=100, textvariable=self.v_per_page, width=6).grid(row=0, column=1, padx=6)
    ttk.Label(row_a, text="Max pages (blank=all)").grid(row=0, column=2, sticky="w")
    ttk.Entry(row_a, textvariable=self.v_max_pages, width=6).grid(row=0, column=3, padx=6)
    ttk.Label(row_a, text="Various policy").grid(row=0, column=4, sticky="w")
    ttk.Combobox(row_a, textvariable=self.v_various, values=["normal", "last", "title"], width=8, state="readonly").grid(row=0, column=5, padx=6)

    # Row B: articles, exclude
    row_b = ttk.Frame(opt1)
    row_b.grid(row=1, column=0, sticky="ew", padx=4, pady=2)
    ttk.Label(row_b, text="Articles-extra (comma)").grid(row=0, column=0, sticky="w")
    ttk.Entry(row_b, textvariable=self.v_articles, width=30).grid(row=0, column=1, padx=6)
    ttk.Label(row_b, text="LNF exclude (semicolon)").grid(row=0, column=2, sticky="w")
    ttk.Entry(row_b, textvariable=self.v_lnf_exclude, width=30).grid(row=0, column=3, padx=6)

    # Row C: toggles
    row_c = ttk.Frame(opt1)
    row_c.grid(row=2, column=0, sticky="ew", padx=4, pady=2)
    for col, (label, var) in enumerate([
      ("LP strict", self.v_lpf_strict),
      ("Debug stats", self.v_debug),
      ("Last-name-first", self.v_lnf),
      ("LNF allow 3", self.v_lnf_allow3),
      ("LNF safe bands", self.v_lnf_safe_bands),
      ("Dividers", self.v_dividers),
      ("TXT align", self.v_align),
      ("Show country", self.v_country),
      ("Also JSON", self.v_json),
    ]):
      ttk.Checkbutton(row_c, text=label, variable=var).grid(row=0, column=col, padx=6, sticky="w")

    # Row D: categories include
    row_d = ttk.Frame(opt1)
    row_d.grid(row=3, column=0, sticky="w", padx=4, pady=2)
    ttk.Checkbutton(row_d, text="Include 45s", variable=self.v_inc_45s).grid(row=0, column=0, padx=6, sticky="w")
    ttk.Checkbutton(row_d, text="Include CDs", variable=self.v_inc_cds).grid(row=0, column=1, padx=6, sticky="w")

    # Actions
    btn_row = ttk.Frame(frm)
    btn_row.grid(row=row, column=0, columnspan=2, sticky="ew", **pad)
    row += 1
    ttk.Button(btn_row, text="Run", command=self._run_clicked).grid(row=0, column=0, padx=4)
    ttk.Button(btn_row, text="Open Output", command=self._open_output).grid(row=0, column=1, padx=4)
    ttk.Button(btn_row, text=self.CLEAN_OUTPUTS_LABEL, command=self._clean_outputs).grid(row=0, column=2, padx=4)
    self.theme_btn = ttk.Button(btn_row, text="☀️ Light Mode", command=self._toggle_theme)
    self.theme_btn.grid(row=0, column=3, padx=4)

    # Log + Output Preview (Tabbed)
    log_fr = ttk.LabelFrame(frm, text="Log")
    log_fr.grid(row=row, column=0, sticky="nsew", **pad)
    nb = ttk.Notebook(frm)
    nb.grid(row=row, column=1, sticky="nsew", **pad)
    frm.rowconfigure(row, weight=1)
    frm.columnconfigure(0, weight=1)
    frm.columnconfigure(1, weight=1)
    import tkinter as tk
    self.log = tk.Text(log_fr, height=16, width=60)
    self.log.pack(fill="both", expand=True)
    self.out_lp = tk.Text(nb, height=16, width=60)
    self.out_45 = tk.Text(nb, height=16, width=60)
    self.out_cd = tk.Text(nb, height=16, width=60)
    nb.add(self.out_lp, text="LPs")
    nb.add(self.out_45, text="45s")
    nb.add(self.out_cd, text="CDs")
    # Default preview target is LPs
    self._out_target = self.out_lp

  def _choose_dir(self) -> None:
    directory = filedialog.askdirectory(initialdir=self.v_output_dir.get() or str(Path.cwd()))
    if directory:
      self.v_output_dir.set(directory)

  def _toggle_theme(self) -> None:
    """Toggle between dark and light mode."""
    self.v_dark_mode.set(not self.v_dark_mode.get())
    self._apply_theme()

  def _apply_theme(self) -> None:
    """Apply the current theme colors to all widgets."""
    if self.v_dark_mode.get():
      self._colors = self._dark_colors.copy()
      self.theme_btn.config(text="🌙 Dark Mode")
    else:
      self._colors = self._light_colors.copy()
      self.theme_btn.config(text="☀️ Light Mode")

    # Update log and output text widgets
    try:
      self.log.config(
        background=self._colors["log_bg"],
        foreground=self._colors["log_fg"],
        insertbackground=self._colors["log_fg"],
      )
      self.out_lp.config(
        background=self._colors["log_bg"],
        foreground=self._colors["log_fg"],
        insertbackground=self._colors["log_fg"],
      )
      self.out_45.config(
        background=self._colors["log_bg"],
        foreground=self._colors["log_fg"],
        insertbackground=self._colors["log_fg"],
      )
      self.out_cd.config(
        background=self._colors["log_bg"],
        foreground=self._colors["log_fg"],
        insertbackground=self._colors["log_fg"],
      )
    except Exception:
      pass

    # Update ttk style for dark mode
    style = ttk.Style()
    if self.v_dark_mode.get():
      try:
        style.configure(".", background=self._colors["panel"], foreground=self._colors["text"])
        style.configure("TFrame", background=self._colors["panel"])
        style.configure("TLabelframe", background=self._colors["panel"])
        style.configure("TLabelframe.Label", background=self._colors["panel"], foreground=self._colors["text"])
        style.configure("TLabel", background=self._colors["panel"], foreground=self._colors["text"])
        style.configure("TCheckbutton", background=self._colors["panel"], foreground=self._colors["text"])
        style.configure("TButton", background=self._colors["bg"])
        style.configure("TEntry", fieldbackground=self._colors["bg"])
        style.configure("TSpinbox", fieldbackground=self._colors["bg"])
        style.configure("TCombobox", fieldbackground=self._colors["bg"])
        style.configure("TNotebook", background=self._colors["panel"])
        style.configure("TNotebook.Tab", background=self._colors["bg"], foreground=self._colors["text"])
        self.root.configure(bg=self._colors["panel"])
      except Exception:
        pass
    else:
      try:
        # Reset to default light theme
        style.configure(".", background="", foreground="")
        style.configure("TFrame", background="")
        style.configure("TLabelframe", background="")
        style.configure("TLabelframe.Label", background="", foreground="")
        style.configure("TLabel", background="", foreground="")
        style.configure("TCheckbutton", background="", foreground="")
        style.configure("TButton", background="")
        style.configure("TEntry", fieldbackground="")
        style.configure("TSpinbox", fieldbackground="")
        style.configure("TCombobox", fieldbackground="")
        style.configure("TNotebook", background="")
        style.configure("TNotebook.Tab", background="", foreground="")
        self.root.configure(bg="")
      except Exception:
        pass

  def log_line(self, text: str) -> None:
    # Queue logs to avoid cross-thread UI access
    self.log_q.put(text + "\n")

  def _pump_logs(self) -> None:
    try:
      while True:
        line = self.log_q.get_nowait()
        self.log.insert("end", line)
        self.log.see("end")
    except queue.Empty:
      pass
    # Output queues (category-tagged lines)
    try:
      while True:
        line = self.out_q.get_nowait()
        # Category header routing: set current target, don't render the header itself
        if line == "LP:\n":
          self._out_target = self.out_lp
          continue
        if line == "45:\n":
          self._out_target = self.out_45
          continue
        if line == "CD:\n":
          self._out_target = self.out_cd
          continue
        target = getattr(self, "_out_target", None) or self.out_lp
        target.insert("end", line)
        target.see("end")
    except queue.Empty:
      pass
    self.root.after(100, self._pump_logs)

  def _open_output(self) -> None:
    path = self.v_output_dir.get().strip() or str(Path.cwd())
    p = Path(path)
    if not p.exists():
      messagebox.showinfo("Output", f"Directory does not exist yet: {p}")
      return
    try:
      if os.name == "posix" and sys.platform == "darwin":  # type: ignore[name-defined]
        subprocess.run(["open", str(p)], check=False)
      else:
        webbrowser.open(str(p))
    except Exception:
      webbrowser.open(str(p))

  def _collect_output_candidates(self, out_dir: Path) -> list[Path]:
    """Collect output files to be deleted."""
    exact = [
      "vinyl_shelf_order.txt",
      "vinyl_shelf_order.csv",
      "vinyl_shelf_order.json",
      "vinyl45_shelf_order.txt",
      "vinyl45_shelf_order.csv",
      "vinyl45_shelf_order.json",
      "cd_shelf_order.txt",
      "cd_shelf_order.csv",
      "cd_shelf_order.json",
      "all_media_shelf_order.json",
    ]
    patterns = ["valuable_over_*kr.txt"]
    candidates = []
    for name in exact:
      p = out_dir / name
      if p.exists():
        candidates.append(p)
    for pat in patterns:
      for p in out_dir.glob(pat):
        if p.is_file():
          candidates.append(p)
    return candidates

  def _clean_outputs(self) -> None:
    # Determine output directory
    base = self.v_output_dir.get().strip() or str(Path.cwd())
    out_dir = Path(base)
    if not out_dir.exists():
      messagebox.showinfo(self.CLEAN_OUTPUTS_LABEL, f"Directory does not exist yet: {out_dir}")
      return
    candidates = self._collect_output_candidates(out_dir)
    if not candidates:
      messagebox.showinfo(self.CLEAN_OUTPUTS_LABEL, "No generated output files found to delete.")
      return
    # Confirm
    names = "\n".join(str(p.name) for p in candidates)
    if not messagebox.askyesno(self.CLEAN_OUTPUTS_LABEL, f"Delete {len(candidates)} files in:\n{out_dir}\n\n{names}"):
      return
    # Delete
    deleted = 0
    for p in candidates:
      try:
        p.unlink(missing_ok=True)  # type: ignore[call-arg]
        deleted += 1
        self.log_line(f"Deleted: {p}")
      except Exception as e:
        self.log_line(f"Failed to delete {p}: {e}")
    messagebox.showinfo(self.CLEAN_OUTPUTS_LABEL, f"Deleted {deleted} file(s).")

  def _run_clicked(self) -> None:
    cfg = RunConfig(
      token=self.v_token.get().strip(),
      user_agent=self.v_user_agent.get().strip() or "VinylSorter/1.0 (+contact)",
      output_dir=self.v_output_dir.get().strip() or str(Path.cwd()),
      per_page=max(1, min(int(self.v_per_page.get() or 100), 100)),
      max_pages=int(self.v_max_pages.get()) if self.v_max_pages.get().strip().isdigit() else None,
      various_policy=self.v_various.get(),
      articles_extra=self.v_articles.get(),
      lp_strict=bool(self.v_lpf_strict.get()),
      debug_stats=bool(self.v_debug.get()),
      last_name_first=bool(self.v_lnf.get()),
      lnf_allow_3=bool(self.v_lnf_allow3.get()),
      lnf_exclude=self.v_lnf_exclude.get(),
      lnf_safe_bands=bool(self.v_lnf_safe_bands.get()),
      dividers=bool(self.v_dividers.get()),
      txt_align=bool(self.v_align.get()),
      show_country=bool(self.v_country.get()),
      write_json=bool(self.v_json.get()),
      include_45s=bool(self.v_inc_45s.get()),
      include_cds=bool(self.v_inc_cds.get()),
    )
    threading.Thread(target=self._run_task, args=(cfg,), daemon=True).start()

  def _run_task(self, cfg: RunConfig) -> None:
    try:
      self.log_line("Starting…")
      username, headers = self._authenticate(cfg)
      out_dir = Path(cfg.output_dir)
      out_dir.mkdir(parents=True, exist_ok=True)
      extra_articles = [a.strip() for a in (cfg.articles_extra or "").split(",") if a.strip()]
      dbg: dict[str, int] | None = {} if cfg.debug_stats else None

      rows_sorted, rows45_sorted, rows_cd_sorted = self._collect_and_sort_rows(cfg, headers, username, extra_articles, dbg)
      if not rows_sorted:
        self.log_line("No matching 33⅓ RPM LPs found.")
        return

      if dbg is not None:
        self.log_line(
          f"Stats: scanned={dbg.get('scanned', 0)}, vinyl={dbg.get('vinyl', 0)}, "
          f"vinyl+LP={dbg.get('vinyl_lp', 0)}, vinyl+LP+33rpm={dbg.get('vinyl_lp_33', 0)}"
        )

      self._write_outputs(cfg, out_dir, rows_sorted, rows45_sorted, rows_cd_sorted)
      self._write_combined_json(cfg, out_dir, rows_sorted, rows45_sorted, rows_cd_sorted)
      self._render_previews(cfg, rows_sorted, rows45_sorted, rows_cd_sorted)
      self._log_summary(rows_sorted, rows45_sorted, rows_cd_sorted)
      self.log_line("Done.")
    except Exception as e:
      self.log_line(f"Error: {e}")
      self.log_line(traceback.format_exc())
      messagebox.showerror("Run failed", str(e))

  def _authenticate(self, cfg: RunConfig):
    token = core.get_token(cfg.token or None)
    headers = core.discogs_headers(token, cfg.user_agent)
    ident = core.get_identity(headers)
    username = ident.get("username")
    if not username:
      raise RuntimeError("Could not determine username from token.")
    self.log_line(f"User: {username}")
    return username, headers

  def _collect_and_sort_rows(self, cfg, headers, username, extra_articles, dbg):
    rows = core.collect_lp_rows(
      headers=headers,
      username=username,
      per_page=cfg.per_page,
      max_pages=cfg.max_pages,
      extra_articles=extra_articles,
      lp_strict=cfg.lp_strict,
      debug_stats=dbg,
      last_name_first=cfg.last_name_first,
      lnf_allow_3=cfg.lnf_allow_3,
      lnf_exclude={core._normalize_exclude_name(s) for s in (cfg.lnf_exclude.split(";") if cfg.lnf_exclude else []) if s.strip()},
      lnf_safe_bands=cfg.lnf_safe_bands,
    )
    rows_sorted = core.sort_rows(rows, cfg.various_policy)
    rows45_sorted: list[ReleaseRow] = []
    rows_cd_sorted: list[ReleaseRow] = []
    if cfg.include_45s:
      rows45 = core.collect_45_rows(
        headers=headers,
        username=username,
        per_page=cfg.per_page,
        max_pages=cfg.max_pages,
        extra_articles=extra_articles,
        last_name_first=cfg.last_name_first,
        lnf_allow_3=cfg.lnf_allow_3,
        lnf_exclude={core._normalize_exclude_name(s) for s in (cfg.lnf_exclude.split(";") if cfg.lnf_exclude else []) if s.strip()},
        lnf_safe_bands=cfg.lnf_safe_bands,
      )
      rows45_sorted = core.sort_rows(rows45, cfg.various_policy)
    if cfg.include_cds:
      rows_cd = core.collect_cd_rows(
        headers=headers,
        username=username,
        per_page=cfg.per_page,
        max_pages=cfg.max_pages,
        extra_articles=extra_articles,
        last_name_first=cfg.last_name_first,
        lnf_allow_3=cfg.lnf_allow_3,
        lnf_exclude={core._normalize_exclude_name(s) for s in (cfg.lnf_exclude.split(";") if cfg.lnf_exclude else []) if s.strip()},
        lnf_safe_bands=cfg.lnf_safe_bands,
      )
      rows_cd_sorted = core.sort_rows(rows_cd, cfg.various_policy)
    return rows_sorted, rows45_sorted, rows_cd_sorted

  def _write_outputs(self, cfg, out_dir, rows_sorted, rows45_sorted, rows_cd_sorted):
    txt_path = out_dir / "vinyl_shelf_order.txt"
    csv_path = out_dir / "vinyl_shelf_order.csv"
    core.write_txt(rows_sorted, txt_path, dividers=cfg.dividers, align=cfg.txt_align, show_country=cfg.show_country)
    core.write_csv(rows_sorted, csv_path)
    self.log_line(f"Wrote: {txt_path}")
    self.log_line(f"Wrote: {csv_path}")
    if cfg.write_json:
      json_path = out_dir / "vinyl_shelf_order.json"
      core.write_json(rows_sorted, json_path)
      self.log_line(f"Wrote: {json_path}")

    if rows45_sorted:
      txt45 = out_dir / "vinyl45_shelf_order.txt"
      csv45 = out_dir / "vinyl45_shelf_order.csv"
      core.write_txt(rows45_sorted, txt45, dividers=cfg.dividers, align=cfg.txt_align, show_country=cfg.show_country)
      core.write_csv(rows45_sorted, csv45)
      self.log_line(f"Wrote: {txt45}")
      self.log_line(f"Wrote: {csv45}")
      if cfg.write_json:
        json45 = out_dir / "vinyl45_shelf_order.json"
        core.write_json(rows45_sorted, json45)
        self.log_line(f"Wrote: {json45}")
    if rows_cd_sorted:
      txtcd = out_dir / "cd_shelf_order.txt"
      csvcd = out_dir / "cd_shelf_order.csv"
      core.write_txt(rows_cd_sorted, txtcd, dividers=cfg.dividers, align=cfg.txt_align, show_country=cfg.show_country)
      core.write_csv(rows_cd_sorted, csvcd)
      self.log_line(f"Wrote: {txtcd}")
      self.log_line(f"Wrote: {csvcd}")
      if cfg.write_json:
        jsoncd = out_dir / "cd_shelf_order.json"
        core.write_json(rows_cd_sorted, jsoncd)
        self.log_line(f"Wrote: {jsoncd}")

  def _write_combined_json(self, cfg, out_dir, rows_sorted, rows45_sorted, rows_cd_sorted):
    if cfg.write_json and (rows45_sorted or rows_cd_sorted):
      import json as _json
      combined = []
      for r in rows_sorted:
        combined.append({"media_type": "LP", **core.rows_to_json([r])[0]})
      for r in rows45_sorted:
        combined.append({"media_type": "45", **core.rows_to_json([r])[0]})
      for r in rows_cd_sorted:
        combined.append({"media_type": "CD", **core.rows_to_json([r])[0]})
      combo_path = out_dir / "all_media_shelf_order.json"
      with combo_path.open("w", encoding="utf-8") as f:
        _json.dump(combined, f, ensure_ascii=False, indent=2)
      self.log_line(f"Wrote: {combo_path}")

  def _render_previews(self, cfg, rows_sorted, rows45_sorted, rows_cd_sorted):
    TRUNCATED_MSG = "... (truncated)\n"
    self.out_q.put("LP:\n")
    for i, line in enumerate(core.generate_txt_lines(rows_sorted, dividers=cfg.dividers, align=cfg.txt_align, show_country=cfg.show_country)):
      if i >= 300:
        self.out_q.put(TRUNCATED_MSG)
        break
      self.out_q.put(line + "\n")
    if rows45_sorted:
      self.out_q.put("45:\n")
      for i, line in enumerate(core.generate_txt_lines(rows45_sorted, dividers=cfg.dividers, align=cfg.txt_align, show_country=cfg.show_country)):
        if i >= 300:
          self.out_q.put(TRUNCATED_MSG)
          break
        self.out_q.put(line + "\n")
    if rows_cd_sorted:
      self.out_q.put("CD:\n")
      for i, line in enumerate(core.generate_txt_lines(rows_cd_sorted, dividers=cfg.dividers, align=cfg.txt_align, show_country=cfg.show_country)):
        if i >= 300:
          self.out_q.put(TRUNCATED_MSG)
          break
        self.out_q.put(line + "\n")

  def _log_summary(self, rows_sorted, rows45_sorted, rows_cd_sorted):
    parts = [f"LP: {len(rows_sorted)}"]
    if rows45_sorted:
      parts.append(f"45s: {len(rows45_sorted)}")
    if rows_cd_sorted:
      parts.append(f"CDs: {len(rows_cd_sorted)}")
    self.log_line("Summary: " + " • ".join(parts))


def main() -> None:
  root = Tk()
  # Basic theming
  try:
    root.call("tk", "scaling", 1.2)
  except Exception:
    pass
  App(root)
  root.mainloop()


if __name__ == "__main__":
  main()
