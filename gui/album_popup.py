import tkinter as tk
from tkinter import messagebox

class AlbumPopup(tk.Toplevel):
    def __init__(self, parent, row, thumbnail_cache, colors, on_spotify=None, on_wishlist=None):
        super().__init__(parent)
        self.title(f"Album Info: {getattr(row, 'artist_display', '')} - {getattr(row, 'title', '')}")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        width, height = 640, 520
        self.geometry(f"{width}x{height}")
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        bg = colors["panel"]
        fg = colors["text"]
        accent = colors["accent"]
        btn_bg = colors["button_bg"]
        btn_fg = colors["button_fg"]
        self.outer = tk.Frame(self, bg=bg, bd=2, relief="ridge")
        self.outer.pack(fill="both", expand=True, padx=8, pady=8)
        # Top section: image + buttons
        top_frame = tk.Frame(self.outer, bg=bg)
        top_frame.pack(pady=(12, 24))
        top_frame.grid_columnconfigure(0, weight=1)
        top_frame.grid_columnconfigure(1, weight=1)
        # Image
        cover_img = None
        if hasattr(thumbnail_cache, 'load_preview') and getattr(row, 'release_id', None):
            cover_img = thumbnail_cache.load_preview(row.release_id, getattr(row, 'cover_image_url', None))
            if not cover_img:
                cover_img = thumbnail_cache.load_photo(row.release_id)
        if not cover_img and hasattr(thumbnail_cache, 'get_placeholder'):
            cover_img = thumbnail_cache.get_placeholder()
        row_offset = 0
        if cover_img:
            img_label = tk.Label(top_frame, image=cover_img, bg=bg)
            img_label.image = cover_img
            img_label.grid(row=0, column=0, padx=(0, 24), sticky="nsew")
            row_offset = 1
        # Button stack
        btn_stack = tk.Frame(top_frame, bg=bg)
        btn_stack.grid(row=0, column=1, sticky="nsew")
        # Spotify button
        if on_spotify:
            btn_spotify = tk.Button(
                btn_stack, text="Play on Spotify", command=lambda: on_spotify(row),
                font=("Segoe UI", 13), bg="#1db954", fg="#fff", activebackground="#1ed760", activeforeground="#fff", relief="groove"
            )
            btn_spotify.pack(side="top", fill="x", padx=12, pady=(0, 8), ipadx=12, ipady=4)
        # Wishlist button
        if on_wishlist:
            btn_wishlist = tk.Button(
                btn_stack, text="Add to Wishlist", command=lambda: on_wishlist(row),
                font=("Segoe UI", 13), bg="#ffb347", fg="#222", activebackground="#ffd580", activeforeground="#222", relief="groove"
            )
            btn_wishlist.pack(side="top", fill="x", padx=12, pady=(0, 8), ipadx=12, ipady=4)
        # Close button
        tk.Button(btn_stack, text="Close", command=self.destroy, font=("Segoe UI", 13), bg=btn_bg, fg=btn_fg, activebackground=accent, activeforeground=btn_fg, relief="groove").pack(side="top", fill="x", padx=12, pady=(0, 0), ipadx=12, ipady=4)
        # Details area
        details_canvas = tk.Canvas(self.outer, bg=bg, highlightthickness=0)
        scrollbar = tk.Scrollbar(self.outer, orient="vertical", command=details_canvas.yview)
        details_canvas.configure(yscrollcommand=scrollbar.set)
        details_canvas.pack(side="left", fill="both", expand=True, padx=(0,0), pady=0)
        scrollbar.pack(side="right", fill="y")
        details_frame = tk.Frame(details_canvas, bg=bg)
        details_canvas.create_window((0,0), window=details_frame, anchor="nw")
        # Populate details
        details = [
            ("Artist", getattr(row, "artist_display", "")),
            ("Title", getattr(row, "title", "")),
            ("Year", getattr(row, "year", "")),
            ("Label", getattr(row, "label", "")),
            ("Catalog #", getattr(row, "catno", "")),
            ("Format", getattr(row, "format_str", getattr(row, "format", ""))),
            ("Country", getattr(row, "country", "")),
            ("Price", f"{getattr(row, 'lowest_price', '')} {getattr(row, 'price_currency', '')}" if getattr(row, "lowest_price", None) is not None else ""),
            ("Discogs ID", getattr(row, "release_id", "")),
            ("Master ID", getattr(row, "master_id", "")),
            ("Barcode", getattr(row, "barcode", "")),
            ("Companies", getattr(row, "companies", "")),
            ("Contributors", getattr(row, "contributors", "")),
            ("URL", getattr(row, "discogs_url", getattr(row, "url", ""))),
            ("Genres", getattr(row, "genres", "")),
            ("Styles", getattr(row, "styles", "")),
            ("Notes", getattr(row, "notes", "")),
            ("Tracklist", getattr(row, "tracklist", "")),
            ("Extra", getattr(row, "extra", "")),
        ]
        for i, (label, value) in enumerate(details):
            if value:
                tk.Label(details_frame, text=label+":", anchor="e", font=("Segoe UI", 14, "bold"), bg=bg, fg=fg).grid(row=i+row_offset, column=0, sticky="e", padx=(0,18), pady=10)
                tk.Label(details_frame, text=str(value), anchor="w", font=("Segoe UI", 14), bg=bg, fg=fg, wraplength=480, justify="left").grid(row=i+row_offset, column=1, sticky="w", padx=(0,12), pady=10)
        # Scroll region
        details_frame.update_idletasks()
        details_canvas.config(scrollregion=details_canvas.bbox("all"))
        def _on_frame_configure(event):
            details_canvas.config(scrollregion=details_canvas.bbox("all"))
        details_frame.bind("<Configure>", _on_frame_configure)
        def _on_mousewheel(event):
            if event.delta:
                direction = -1 if event.delta > 0 else 1
                details_canvas.yview_scroll(direction, "units")
            elif hasattr(event, 'num'):
                if event.num == 4:
                    details_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    details_canvas.yview_scroll(1, "units")
            return "break"
        details_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        details_canvas.bind_all("<Button-4>", _on_mousewheel)
        details_canvas.bind_all("<Button-5>", _on_mousewheel)
        def _unbind_mousewheel():
            details_canvas.unbind_all("<MouseWheel>")
            details_canvas.unbind_all("<Button-4>")
            details_canvas.unbind_all("<Button-5>")
        self.protocol("WM_DELETE_WINDOW", lambda: (self.destroy(), _unbind_mousewheel()))
