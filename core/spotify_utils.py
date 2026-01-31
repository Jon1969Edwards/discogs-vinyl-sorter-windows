import webbrowser
import urllib.parse

def open_album_on_spotify(artist: str, album: str):
    """Open the Spotify search page for the given artist and album."""
    query = f"album:{album} artist:{artist}"
    # Try to open the Spotify desktop app using the spotify:search: URI
    import os, sys
    spotify_uri = f"spotify:search:{urllib.parse.quote(query)}"
    try:
        if sys.platform.startswith("win"):
            os.startfile(spotify_uri)
            return
        elif sys.platform.startswith("darwin"):
            os.system(f"open '{spotify_uri}'")
            return
        else:
            os.system(f"xdg-open '{spotify_uri}'")
            return
    except Exception:
        pass
    # Fallback: open in browser
    url = f"https://open.spotify.com/search/{urllib.parse.quote(query)}"
    webbrowser.open(url)
