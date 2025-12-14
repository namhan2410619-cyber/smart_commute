# utils/map_utils.py
import requests
from utils.api_keys import NOMINATIM_USER_AGENT
from functools import lru_cache

@lru_cache(maxsize=512)
def geocode(address: str):
    """
    address -> (lat, lon)
    uses Nominatim with caching. Raises ValueError if not found.
    """
    if not address:
        raise ValueError("empty address")
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": NOMINATIM_USER_AGENT}
    params = {"q": address, "format": "json", "limit": 1}
    resp = requests.get(url, params=params, headers=headers, timeout=8)
    resp.raise_for_status()
    j = resp.json()
    if not j:
        raise ValueError("address not found")
    return float(j[0]["lat"]), float(j[0]["lon"])
