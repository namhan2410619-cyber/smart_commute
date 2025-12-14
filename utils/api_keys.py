# utils/api_keys.py
import os
from dotenv import load_dotenv

# load local .env if present (local dev). Streamlit Cloud will use st.secrets.
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
env_path = os.path.join(_root, ".env")
load_dotenv(dotenv_path=env_path)

def _get(key, default=None):
    v = os.getenv(key)
    if v:
        return v
    # if running under Streamlit cloud, user can set st.secrets - the main app reads those
    return default

BUS_API_KEY = _get("BUS_API_KEY")
WEATHER_API_KEY = _get("WEATHER_API_KEY")
SUBWAY_API_KEY = _get("SUBWAY_API_KEY")
TRAFFIC_API_KEY = _get("TRAFFIC_API_KEY")
CROSSROAD_API_KEY = _get("CROSSROAD_API_KEY")
TRAFFIC_LIGHT_API_KEY = _get("TRAFFIC_LIGHT_API_KEY")
NOMINATIM_USER_AGENT = _get("NOMINATIM_USER_AGENT", "smart-commute-agent")
