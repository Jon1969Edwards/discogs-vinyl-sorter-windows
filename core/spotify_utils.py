import webbrowser
import urllib.parse

def open_album_on_spotify(artist: str, album: str):
    """Open the Spotify search page for the given artist and album."""
    query = f"album:{album} artist:{artist}"
    url = f"https://open.spotify.com/search/{urllib.parse.quote(query)}"
    webbrowser.open(url)
