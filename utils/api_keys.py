# utils/api_keys.py
import os

# try streamlit secrets first (when deployed in Streamlit Cloud)
SECRETS = None
try:
    import streamlit as _st
    SECRETS = _st.secrets
except Exception:
    SECRETS = None

def get_secret(key, default=None):
    v = os.getenv(key)
    if v:
        return v
    if SECRETS and key in SECRETS:
        return SECRETS[key]
    return default

BUS_API_KEY = get_secret("BUS_API_KEY")
WEATHER_API_KEY = get_secret("WEATHER_API_KEY")
SUBWAY_API_KEY = get_secret("SUBWAY_API_KEY")
TRAFFIC_API_KEY = get_secret("TRAFFIC_API_KEY")
CROSSROAD_API_KEY = get_secret("CROSSROAD_API_KEY")
TRAFFIC_LIGHT_API_KEY = get_secret("TRAFFIC_LIGHT_API_KEY")
NOMINATIM_USER_AGENT = get_secret("NOMINATIM_USER_AGENT", "smart-commute-agent")
