"""In-popup audio preview controls for album info dialogs."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from typing import Callable, Optional

from core.audio_preview import AudioPreview, find_audio_preview
from core.preview_player import PreviewPlayer
from core.spotify_utils import open_album_on_spotify
from gui.constants import FONT_MD, FONT_SEGOE_UI, FONT_SM, FONT_XS


class AudioPreviewPanel(tk.Frame):
    """Preview player widget shown in album info popups."""

    def __init__(
        self,
        master,
        *,
        artist: str,
        album: str,
        release_id: Optional[int],
        get_headers: Callable[[], dict],
        bg: str,
        fg: str,
        accent: str,
        on_destroy: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master, bg=bg)
        self._artist = artist
        self._album = album
        self._release_id = release_id
        self._get_headers = get_headers
        self._fg = fg
        self._accent = accent
        self._preview: Optional[AudioPreview] = None
        self._lookup_done = False
        self._lookup_thread: Optional[threading.Thread] = None
        self._player = PreviewPlayer()
        self._on_destroy = on_destroy

        self._status = tk.StringVar(value="")
        self._action_text = tk.StringVar(value="▶ Play sample")

        self._action_btn = tk.Button(
            self,
            textvariable=self._action_text,
            command=self._on_action,
            font=(FONT_SEGOE_UI, FONT_MD),
            bg="#6c63ff",
            fg="#ffffff",
            activebackground="#7d75ff",
            activeforeground="#ffffff",
            relief="groove",
            width=18,
        )
        self._action_btn.pack(fill="x", padx=12, pady=(0, 4), ipadx=12, ipady=4)

        self._detail = tk.Label(
            self,
            textvariable=self._status,
            font=(FONT_SEGOE_UI, FONT_XS),
            bg=bg,
            fg=fg,
            wraplength=220,
            justify="center",
        )
        self._detail.pack(fill="x", padx=12, pady=(0, 4))

        spotify_link = tk.Label(
            self,
            text="Search on Spotify",
            font=(FONT_SEGOE_UI, FONT_SM, "underline"),
            bg=bg,
            fg="#1db954",
            cursor="hand2",
        )
        spotify_link.pack(pady=(0, 8))
        spotify_link.bind(
            "<Button-1>",
            lambda _e: open_album_on_spotify(self._artist, self._album),
        )

        self.bind("<Destroy>", self._handle_destroy)

    def _handle_destroy(self, _event=None) -> None:
        self._player.stop()
        if self._on_destroy:
            self._on_destroy()

    def _set_status(self, text: str) -> None:
        self.after(0, lambda: self._status.set(text))

    def _set_action(self, text: str, *, enabled: bool = True) -> None:
        def apply() -> None:
            self._action_text.set(text)
            self._action_btn.config(state="normal" if enabled else "disabled")

        self.after(0, apply)

    def _on_action(self) -> None:
        if self._player.is_playing():
            self._player.stop()
            self._apply_preview_ui()
            return

        if self._preview:
            self._start_preview(self._preview)
            return

        if self._lookup_thread and self._lookup_thread.is_alive():
            return

        self._set_action("Searching…", enabled=False)
        self._set_status("Looking for a preview…")
        self._lookup_thread = threading.Thread(target=self._lookup_preview, daemon=True)
        self._lookup_thread.start()

    def _lookup_preview(self) -> None:
        try:
            headers = self._get_headers()
            preview = find_audio_preview(
                self._artist,
                self._album,
                release_id=self._release_id,
                headers=headers,
            )
        except Exception:
            preview = None

        self._lookup_done = True
        self._preview = preview

        def apply_result() -> None:
            self._apply_preview_ui()
            if preview:
                self._start_preview(preview)

        self.after(0, apply_result)

    def _apply_preview_ui(self) -> None:
        if self._player.is_playing():
            self._set_action("⏹ Stop")
            return

        preview = self._preview
        if not preview:
            if self._lookup_done:
                self._set_action("No preview found", enabled=False)
                self._set_status("Try Spotify or Discogs below.")
            else:
                self._set_action("▶ Play sample")
                self._set_status("")
            return

        if preview.kind == "youtube":
            self._set_action("▶ Watch on YouTube")
            self._set_status(f"{preview.title}\n({preview.source})")
            return

        detail = f"♪ {preview.title}\n(30 sec · {preview.source})"
        self._set_status(detail)
        self._set_action("▶ Play sample")

    def _start_preview(self, preview: AudioPreview) -> None:
        if preview.kind == "youtube":
            webbrowser.open(preview.url)
            return

        if not PreviewPlayer.is_available():
            self._set_status("Install pygame to play previews.")
            self._set_action("▶ Play sample")
            return

        self._set_action("Loading…", enabled=False)

        def on_started() -> None:
            self._set_action("⏹ Stop")
            self._set_status(f"♪ {preview.title}\n(30 sec · {preview.source})")

        def on_finished() -> None:
            self._apply_preview_ui()

        def on_error(message: str) -> None:
            self._set_status(f"Playback failed: {message}")
            self._apply_preview_ui()

        self._player.play(
            preview.url,
            on_started=on_started,
            on_finished=on_finished,
            on_error=on_error,
        )
