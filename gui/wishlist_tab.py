"""
WishlistTab: Encapsulates the wishlist tab logic/UI for the Discogs Vinyl Sorter app.

- Handles wishlist display, album cover thumbnails, info popups, and actions.
- Designed to be imported and used by the main App class in autosort_gui.py.

Dependencies:
- ttkbootstrap or tkinter.ttk
- PIL (Pillow) for images (optional, for thumbnails)
- AlbumPopup from gui.album_popup
- core.wishlist for wishlist data
"""

import tkinter as tk
from tkinter import ttk
from gui.album_popup import AlbumPopup
from core.wishlist import load_wishlist

class WishlistTab:
    def __init__(self, parent, thumbnail_cache=None, colors=None):
        self.parent = parent
        self.thumbnail_cache = thumbnail_cache
        self.colors = colors or {}
        self.frame = ttk.Frame(parent)
        self.tree = None
        self._album_popup = None
        self._setup_ui()

    def _setup_ui(self):
        # Treeview for wishlist
        columns = ("Artist", "Title", "Notes", "Release ID")
        self.tree = ttk.Treeview(self.frame, columns=columns, show="headings", height=18)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120 if col != "Notes" else 200, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Motion>", self._on_motion)
        self.tree.bind("<Leave>", self._on_leave)
        self._album_popup = None
        self._populate()

    def _populate(self):
        self.tree.delete(*self.tree.get_children())
        for entry in load_wishlist():
            artist = entry.get("artist", "")
            title = entry.get("title", "")
            notes = entry.get("notes", "")
            release_id = entry.get("release_id", "")
            self.tree.insert("", "end", values=(artist, title, notes, release_id))

    def _on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        values = self.tree.item(item, "values")
        artist, title, notes, release_id = values
        # Find the wishlist entry
        entry = None
        for w in load_wishlist():
            if w["artist"] == artist and w["title"] == title:
                entry = w
                break
        if not entry:
            return
        # Show album popup
        if self._album_popup:
            self._album_popup.destroy()
        self._album_popup = AlbumPopup(self.parent, entry, self.thumbnail_cache)

    def _on_motion(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            if self._album_popup:
                self._album_popup.hide()
            return
        values = self.tree.item(item, "values")
        artist, title, *_ = values
        entry = None
        for w in load_wishlist():
            if w["artist"] == artist and w["title"] == title:
                entry = w
                break
        if not entry:
            return
        release_id = entry.get("release_id")
        thumb_url = entry.get("thumb") or entry.get("cover_image_url")
        img = None
        if self.thumbnail_cache and release_id:
            img = self.thumbnail_cache.get_photo(release_id)
        if not img and self.thumbnail_cache and thumb_url:
            img = self.thumbnail_cache.load_preview(release_id or 0, thumb_url)
        if not img and self.thumbnail_cache:
            img = self.thumbnail_cache.get_placeholder()
        # Optionally show a preview popup (if implemented)
        # (This is a stub; main app may handle preview popups)

    def _on_leave(self, event):
        if self._album_popup:
            self._album_popup.hide()

    def get_frame(self):
        return self.frame

    def refresh(self):
        self._populate()
