# utils/map_utils.py
import requests
from utils.api_keys import NOMINATIM_USER_AGENT
from functools import lru_cache

@lru_cache(maxsize=256)
def geocode(address):
    """
    address: 문자열 주소
    returns: (lat, lon) or raises ValueError
    """
    if not address:
        raise ValueError("address empty")
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": NOMINATIM_USER_AGENT}
    params = {"q": address, "format": "json", "limit": 1}
    r = requests.get(url, params=params, headers=headers, timeout=8)
    r.raise_for_status()
    j = r.json()
    if not j:
        raise ValueError("address not found")
    return float(j[0]["lat"]), float(j[0]["lon"])
