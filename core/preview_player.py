"""Play short MP3 preview streams for the album info popup."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

try:
    import requests  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    requests = None  # type: ignore

try:
    import pygame  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    pygame = None  # type: ignore


class PreviewPlayer:
    """Download and play a short MP3 preview."""

    _mixer_ready = False
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._temp_path: Optional[Path] = None
        self._playing = False

    @classmethod
    def is_available(cls) -> bool:
        return pygame is not None and requests is not None

    @classmethod
    def _ensure_mixer(cls) -> None:
        if cls._mixer_ready or pygame is None:
            return
        with cls._lock:
            if not cls._mixer_ready:
                pygame.mixer.init()
                cls._mixer_ready = True

    def play(
        self,
        url: str,
        *,
        on_started: Optional[Callable[[], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Download and play a preview URL on a background thread."""

        def worker() -> None:
            try:
                if requests is None or pygame is None:
                    raise RuntimeError("Audio playback dependencies are not installed.")
                self.stop()
                resp = requests.get(url, timeout=20)
                resp.raise_for_status()
                suffix = ".mp3"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(resp.content)
                    path = Path(tmp.name)
                self._temp_path = path
                self._ensure_mixer()
                pygame.mixer.music.load(str(path))
                pygame.mixer.music.play()
                self._playing = True
                if on_started:
                    on_started()
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(100)
                self._playing = False
                self._cleanup_temp()
                if on_finished:
                    on_finished()
            except Exception as exc:
                self._playing = False
                self._cleanup_temp()
                if on_error:
                    on_error(str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def stop(self) -> None:
        if pygame is not None:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self._playing = False
        self._cleanup_temp()

    def is_playing(self) -> bool:
        if pygame is not None:
            try:
                return self._playing or pygame.mixer.music.get_busy()
            except Exception:
                return self._playing
        return self._playing

    def _cleanup_temp(self) -> None:
        if self._temp_path and self._temp_path.exists():
            try:
                self._temp_path.unlink()
            except Exception:
                pass
        self._temp_path = None
