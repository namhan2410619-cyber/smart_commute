# agents/data_agent.py
import time, math, requests
import xmltodict
from utils.api_keys import BUS_API_KEY, WEATHER_API_KEY, SUBWAY_API_KEY, TRAFFIC_API_KEY, NOMINATIM_USER_AGENT
from utils.map_utils import geocode
from functools import lru_cache

class DataAgent:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": NOMINATIM_USER_AGENT})
        self.cache = {}

    # ----------------- lat/lon -> KMA grid -----------------
    def _latlon_to_grid(self, lat, lon):
        RE = 6371.00877
        GRID = 5.0
        SLAT1 = 30.0
        SLAT2 = 60.0
        OLON = 126.0
        OLAT = 38.0
        XO = 43
        YO = 136

        DEGRAD = math.pi / 180.0
        re = RE / GRID
        slat1 = SLAT1 * DEGRAD
        slat2 = SLAT2 * DEGRAD
        olon = OLON * DEGRAD
        olat = OLAT * DEGRAD

        sn = math.tan(math.pi*0.25 + slat2*0.5) / math.tan(math.pi*0.25 + slat1*0.5)
        sn = math.log(math.cos(slat1)/math.cos(slat2)) / math.log(sn)
        sf = math.tan(math.pi*0.25 + slat1*0.5)
        sf = (sf**sn * math.cos(slat1)) / sn
        ro = math.tan(math.pi*0.25 + olat*0.5)
        ro = re * sf / (ro**sn)
        ra = math.tan(math.pi*0.25 + (lat*DEGRAD)*0.5)
        ra = re * sf / (ra**sn)
        theta = lon*DEGRAD - olon
        if theta > math.pi: theta -= 2.0*math.pi
        if theta < -math.pi: theta += 2.0*math.pi
        theta *= sn
        x = (ra*math.sin(theta)) + XO + 0.5
        y = (ro - ra*math.cos(theta)) + YO + 0.5
        return int(x), int(y)

    # ----------------- weather (KMA short-term) -----------------
    def get_weather_for_coord(self, coord):
        try:
            lat, lon = coord
            nx, ny = self._latlon_to_grid(lat, lon)
            base_date = time.strftime("%Y%m%d")
            # choose base_time: common safe time 0500/0800/1100... a better approach would compute latest base_time
            base_time = "0500"
            url = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
            params = {
                "serviceKey": WEATHER_API_KEY,
                "pageNo": "1",
                "numOfRows": "1000",
                "dataType": "JSON",
                "base_date": base_date,
                "base_time": base_time,
                "nx": nx,
                "ny": ny
            }
            r = self.session.get(url, params=params, timeout=8)
            r.raise_for_status()
            j = r.json()
            items = j.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            # simple rule: if any PTY>0 or POP>50 in the near future, consider rain
            rain = False
            for it in items:
                cat = it.get("category")
                if cat in ("PTY","POP"):
                    try:
                        val = int(it.get("fcstValue",0))
                        if val >= 30:
                            rain = True
                            break
                    except:
                        continue
            return {"raw": j, "rain": rain}
        except Exception:
            return {"raw": None, "rain": False}

    # ----------------- bus ETA (fallback) -----------------
    def get_bus_eta_for_coord(self, coord, station_id=None):
        # if station_id provided, call API; otherwise fallback heuristic (5 min)
        if not station_id:
            return 5
        try:
            url = "https://apis.data.go.kr/6410000/busarrivalservice/v2/arrivalsByRoute"
            params = {"serviceKey": BUS_API_KEY, "stationId": station_id, "format":"json"}
            r = self.session.get(url, params=params, timeout=6)
            r.raise_for_status()
            j = r.json()
            arrs = j.get("response", {}).get("busArrivalList", [])
            if arrs:
                return int(arrs[0].get("predictTime1", 0))
            return 10
        except Exception:
            return 10

    # ----------------- subway ETA (fallback) -----------------
    def get_subway_eta_for_station(self, station_name=None):
        if not station_name:
            return 3
        try:
            url = f"http://swopenAPI.seoul.go.kr/api/subway/{SUBWAY_API_KEY}/json/realtimeStationArrival/0/5/{station_name}"
            r = self.session.get(url, timeout=6)
            r.raise_for_status()
            j = r.json()
            arrs = j.get("realtimeArrivalList", [])
            if arrs:
                sec = int(arrs[0].get("barvlDt", 0))
                return max(1, sec//60)
            return 5
        except Exception:
            return 5

    # ----------------- traffic heuristic -----------------
    def get_traffic_delay(self, start_coord, end_coord):
        # simple heuristic: distance + peak hour penalty
        def haversine(a,b):
            R = 6371.0
            lat1, lon1 = map(math.radians, a)
            lat2, lon2 = map(math.radians, b)
            dlat = lat2 - lat1; dlon = lon2 - lon1
            aa = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
            c = 2*math.atan2(math.sqrt(aa), math.sqrt(1-aa))
            return R*c
        dist = haversine(start_coord, end_coord)
        now_h = time.localtime().tm_hour
        peak = (7 <= now_h <= 9) or (17 <= now_h <= 19)
        base = 3 if dist < 2 else 8
        return base + (7 if peak else 0)

    # ----------------- crossings & lights -----------------
    def get_crossings_count(self, start_coord, end_coord):
        km = self.get_distance_km(start_coord, end_coord)
        return max(0, int(km / 0.6))

    def get_crossing_points(self, start_coord, end_coord):
        cnt = self.get_crossings_count(start_coord, end_coord)
        if cnt == 0: return []
        lat1,lon1 = start_coord; lat2,lon2 = end_coord
        pts = []
        for i in range(1, cnt+1):
            frac = i/(cnt+1)
            pts.append((lat1 + (lat2-lat1)*frac, lon1 + (lon2-lon1)*frac, 60))
        return pts

    def traffic_light_delay(self, crossings_count):
        MAX_WAIT = 90
        return (crossings_count * MAX_WAIT) // 60

    def get_distance_km(self, a, b):
        R=6371.0
        lat1,lon1=map(math.radians,a)
        lat2,lon2=map(math.radians,b)
        dlat=lat2-lat1; dlon=lon2-lon1
        aa=math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        c=2*math.atan2(math.sqrt(aa), math.sqrt(1-aa))
        return R*c
