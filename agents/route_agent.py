# agents/route_agent.py
import requests, math

class RouteAgent:
    def __init__(self):
        pass

    def haversine_km(self, a, b):
        R=6371.0
        lat1,lon1=map(math.radians,a)
        lat2,lon2=map(math.radians,b)
        dlat=lat2-lat1; dlon=lon2-lon1
        aa=math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        c=2*math.atan2(math.sqrt(aa), math.sqrt(1-aa))
        return R*c

    def estimate_walk_minutes(self, start, end, speed_kmh=4.5):
        km = self.haversine_km(start, end)
        return max(1, int((km / speed_kmh) * 60))

    def estimate_bus_minutes(self, start, end):
        km = self.haversine_km(start, end)
        return max(1, int((km / 25) * 60))

    def estimate_subway_minutes(self, start, end):
        km = self.haversine_km(start, end)
        return max(1, int((km / 40) * 60))

    def get_osrm_coords(self, start, end, mode="walking"):
        try:
            lon1,lat1 = start[1], start[0]
            lon2,lat2 = end[1], end[0]
            url = f"https://router.project-osrm.org/route/v1/{mode}/{lon1},{lat1};{lon2},{lat2}"
            params = {"overview":"full","geometries":"geojson"}
            r = requests.get(url, params=params, timeout=8)
            r.raise_for_status()
            data = r.json()
            coords = data["routes"][0]["geometry"]["coordinates"]
            return [(lat, lon) for lon,lat in coords]
        except Exception:
            return []
