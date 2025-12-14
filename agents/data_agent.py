# agents/data_agent.py
import requests, math, time
from utils.api_keys import BUS_API_KEY, WEATHER_API_KEY, SUBWAY_API_KEY, TRAFFIC_API_KEY
from utils.map_utils import geocode

class DataAgent:
    def __init__(self):
        self.session = requests.Session()
        # small in-memory cache
        self._cache = {}

    # ---------- weather (KMA simple) ----------
    def _latlon_to_grid(self, lat, lon):
        # conversion used earlier — returns (nx, ny)
        RE=6371.00877; GRID=5.0; SLAT1=30.0; SLAT2=60.0; OLON=126.0; OLAT=38.0; XO=43; YO=136
        DEGRAD=math.pi/180.0
        re=RE/GRID
        slat1=SLAT1*DEGRAD; slat2=SLAT2*DEGRAD; olon=OLON*DEGRAD; olat=OLAT*DEGRAD
        sn=math.tan(math.pi*0.25+slat2*0.5)/math.tan(math.pi*0.25+slat1*0.5)
        sn=math.log(math.cos(slat1)/math.cos(slat2))/math.log(sn)
        sf=math.tan(math.pi*0.25+slat1*0.5); sf=(sf**sn*math.cos(slat1))/sn
        ro=math.tan(math.pi*0.25+olat*0.5); ro=re*sf/(ro**sn)
        ra=math.tan(math.pi*0.25+(lat*DEGRAD)*0.5); ra=re*sf/(ra**sn)
        theta=lon*DEGRAD-olon
        if theta>math.pi: theta-=2.0*math.pi
        if theta<-math.pi: theta+=2.0*math.pi
        theta*=sn
        x=(ra*math.sin(theta))+XO+0.5
        y=(ro-ra*math.cos(theta))+YO+0.5
        return int(x), int(y)

    def get_weather(self, coord):
        """
        Returns dict: {'rain': bool, 'raw': ...}
        If API missing / error, returns fallback {'rain':False}
        """
        try:
            lat, lon = coord
            nx, ny = self._latlon_to_grid(lat, lon)
            base_date = time.strftime("%Y%m%d")
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
            rain = False
            for it in items:
                if it.get("category") in ("PTY", "POP"):
                    try:
                        if int(it.get("fcstValue",0)) >= 30:
                            rain = True
                            break
                    except:
                        continue
            return {"rain": rain, "raw": j}
        except Exception:
            return {"rain": False, "raw": None}

    # ---------- traffic heuristic ----------
    def get_traffic_delay(self, start_coord, end_coord):
        # simple heuristic based on distance and peak hours
        def haversine(a,b):
            R=6371.0
            lat1,lon1=map(math.radians,a)
            lat2,lon2=map(math.radians,b)
            dlat=lat2-lat1; dlon=lon2-lon1
            aa=math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
            c=2*math.atan2(math.sqrt(aa), math.sqrt(1-aa))
            return R*c
        dist = haversine(start_coord, end_coord)
        now_h = time.localtime().tm_hour
        peak = (7 <= now_h <= 9) or (17 <= now_h <= 19)
        base = 3 if dist < 2 else 8
        return base + (7 if peak else 0)

    # ---------- bus/subway ETA simple wrappers (fall back if API missing) ----------
    def get_bus_eta(self, coord=None, station_id=None):
        if not BUS_API_KEY or not station_id:
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

    def get_subway_eta(self, station=None, line_no=None):
        if not SUBWAY_API_KEY or not station:
            return 3
        try:
            url = f"http://swopenAPI.seoul.go.kr/api/subway/{SUBWAY_API_KEY}/json/realtimeStationArrival/0/5/{station}"
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

    # ---------- traffic light / crossings (fallback heuristic) ----------
    def get_crossings_info(self, start_coord, end_coord):
        # returns list of (lat, lon, max_wait_seconds)
        # If API exists, call it; else create points every ~0.6km and max_wait 60s
        km = self.get_distance_km(start_coord, end_coord)
        cnt = max(0, int(km / 0.6))
        pts = []
        if cnt == 0:
            return pts
        lat1, lon1 = start_coord; lat2, lon2 = end_coord
        for i in range(1, cnt+1):
            frac = i / (cnt + 1)
            pts.append((lat1 + (lat2-lat1)*frac, lon1 + (lon2-lon1)*frac, 60))
        return pts

    def traffic_light_penalty_minutes(self, crossings):
        # take maximum wait among crossings, convert to minutes
        if not crossings:
            return 0
        max_wait = max([w for (_,_,w) in crossings])
        return (max_wait // 60)

    def get_distance_km(self, a, b):
        R=6371.0
        lat1,lon1=map(math.radians,a)
        lat2,lon2=map(math.radians,b)
        dlat=lat2-lat1; dlon=lon2-lon1
        aa=math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        c=2*math.atan2(math.sqrt(aa), math.sqrt(1-aa))
        return R*c
