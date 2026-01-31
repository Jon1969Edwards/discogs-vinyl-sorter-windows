import requests

def fetch_discogs_wantlist(token: str, per_page: int = 100):
    """Fetch the user's wantlist from Discogs API."""
    headers = {
        "Authorization": f"Discogs token={token}",
        "User-Agent": "VinylSorter/1.0 +https://github.com/youruser/vinylsorter"
    }
    # Get username
    resp = requests.get("https://api.discogs.com/oauth/identity", headers=headers)
    resp.raise_for_status()
    username = resp.json()["username"]
    # Fetch wantlist
    wantlist = []
    page = 1
    while True:
        url = f"https://api.discogs.com/users/{username}/wants?page={page}&per_page={per_page}"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        for item in data["wants"]:
            basic = item["basic_information"]
            wantlist.append({
                "artist": ", ".join(a["name"] for a in basic["artists"]),
                "title": basic["title"],
                "year": basic.get("year"),
                "discogs_url": basic["resource_url"],
                "thumb": basic.get("thumb", "")
            })
        if data["pagination"]["page"] >= data["pagination"]["pages"]:
            break
        page += 1
    return wantlist
