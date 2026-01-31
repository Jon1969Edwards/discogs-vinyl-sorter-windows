# wishlist.py
# Simple wishlist management for Discogs Vinyl Sorter
import json
from pathlib import Path

WISHLIST_FILE = Path("wishlist.json")

def load_wishlist():
    if WISHLIST_FILE.exists():
        with open(WISHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_wishlist(wishlist):
    with open(WISHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(wishlist, f, indent=2, ensure_ascii=False)

def add_to_wishlist(artist, title, discogs_url=None):
    wishlist = load_wishlist()
    entry = {"artist": artist, "title": title, "discogs_url": discogs_url}
    if entry not in wishlist:
        wishlist.append(entry)
        save_wishlist(wishlist)
        return True
    return False

def remove_from_wishlist(artist, title):
    wishlist = load_wishlist()
    wishlist = [w for w in wishlist if not (w["artist"] == artist and w["title"] == title)]
    save_wishlist(wishlist)

def is_in_wishlist(artist, title):
    wishlist = load_wishlist()
    return any(w["artist"] == artist and w["title"] == title for w in wishlist)
