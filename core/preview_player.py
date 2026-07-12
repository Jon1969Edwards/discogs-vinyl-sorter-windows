"""Play short MP3 preview streams for the album info popup."""

from __future__ import annotations

import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path
from typing import Callable, Optional

try:
    import requests  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    requests = None  # type: ignore

_pygame = None
_pygame_checked = False


def _get_pygame():
    """Lazy-load pygame so installs take effect without restarting imports."""
    global _pygame, _pygame_checked
    if _pygame_checked:
        return _pygame
    _pygame_checked = True
    try:
        import pygame  # type: ignore

        _pygame = pygame
    except ModuleNotFoundError:
        _pygame = None
    return _pygame


def _suffix_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    for ext in (".mp3", ".m4a", ".aac", ".wav"):
        if path.endswith(ext):
            return ext
    lowered = url.lower()
    if ".m4a" in lowered or ".aac" in lowered:
        return ".m4a"
    if ".wav" in lowered:
        return ".wav"
    return ".mp3"


class PreviewPlayer:
    """Download and play a short preview clip."""

    _mixer_ready = False
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._temp_path: Optional[Path] = None
        self._playing = False

    @classmethod
    def is_available(cls) -> bool:
        return _get_pygame() is not None and requests is not None

    @classmethod
    def _ensure_mixer(cls) -> None:
        pygame = _get_pygame()
        if cls._mixer_ready or pygame is None:
            return
        with cls._lock:
            if not cls._mixer_ready and pygame is not None:
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
            pygame = _get_pygame()
            try:
                if requests is None or pygame is None:
                    raise RuntimeError(
                        "Audio playback requires pygame. Run SETUP.bat or: pip install pygame"
                    )
                self.stop()
                resp = requests.get(url, timeout=20)
                resp.raise_for_status()
                suffix = _suffix_from_url(url)
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(resp.content)
                    path = Path(tmp.name)
                self._temp_path = path
                self._ensure_mixer()
                try:
                    pygame.mixer.music.load(str(path))
                except Exception as exc:
                    if suffix != ".mp3":
                        raise RuntimeError(
                            "This preview format is not supported. Try again — Deezer previews usually work."
                        ) from exc
                    raise
                pygame.mixer.music.play()
                self._playing = True
                if on_started:
                    on_started()
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(100)
                self._playing = False
                self._release_file()
                if on_finished:
                    on_finished()
            except Exception as exc:
                self._playing = False
                self._release_file()
                if on_error:
                    on_error(str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def stop(self) -> None:
        pygame = _get_pygame()
        if pygame is not None:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except Exception:
                pass
        self._playing = False
        self._release_file()

    def is_playing(self) -> bool:
        pygame = _get_pygame()
        if pygame is not None:
            try:
                return self._playing or pygame.mixer.music.get_busy()
            except Exception:
                return self._playing
        return self._playing

    def _release_file(self) -> None:
        if self._temp_path and self._temp_path.exists():
            try:
                self._temp_path.unlink()
            except OSError:
                if sys.platform.startswith("win"):
                    # File may still be locked briefly after pygame unload.
                    delayed = self._temp_path

                    def cleanup() -> None:
                        try:
                            delayed.unlink(missing_ok=True)
                        except OSError:
                            pass

                    threading.Timer(1.0, cleanup).start()
        self._temp_path = None
