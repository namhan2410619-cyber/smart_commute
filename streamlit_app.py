# streamlit_app.py
import streamlit as st
from datetime import datetime, timedelta
from agents.data_agent import DataAgent
from agents.route_agent import RouteAgent
from agents.schedule_agent import ScheduleAgent
from utils.map_utils import geocode
from utils.api_keys import NOMINATIM_USER_AGENT

from streamlit_folium import st_folium
import folium
import time

st.set_page_config(page_title="Smart Commute", layout="wide")
st.title("Smart Commute — 통학 알람 (브라우저 알림)")

# 좌측 패널 - 입력
st.sidebar.header("설정")
start_addr = st.sidebar.text_input("출발지 주소", "서울특별시 중구 세종대로 110")
end_addr = st.sidebar.text_input("도착지 주소", "서울특별시 강남구 역삼동")
target_time = st.sidebar.text_input("등교(도착) 목표 시간 (HH:MM)", "08:40")
prep_minutes = st.sidebar.number_input("준비 시간(분)", min_value=5, max_value=120, value=30)
allow_walk = st.sidebar.checkbox("도보 허용", value=True)
allow_bus = st.sidebar.checkbox("버스 허용", value=True)
allow_subway = st.sidebar.checkbox("지하철 허용", value=True)

if st.sidebar.button("계산"):
    with st.spinner("주소 변환 중..."):
        try:
            start_coord = geocode(start_addr)
            end_coord = geocode(end_addr)
        except Exception as e:
            st.error(f"주소 변환 실패: {e}")
            st.stop()

    da = DataAgent()
    ra = RouteAgent()

    # 실시간 정보
    weather = da.get_weather_for_coord(start_coord)
    traffic_delay = da.get_traffic_delay(start_coord, end_coord)
    crossings = da.get_crossings_count(start_coord, end_coord)
    crossing_points = da.get_crossing_points(start_coord, end_coord)
    signal_delay = da.traffic_light_delay(crossings)

    # 거리 기반 ETA
    km = da.get_distance_km(start_coord, end_coord)
    walk_time = ra.estimate_walk_time_km(km)
    bus_time = ra.estimate_bus_time(start_coord, end_coord)
    subway_time = ra.estimate_subway_time(start_coord, end_coord)

    # build options dict
    options = []
    if allow_walk:
        options.append(("walk", walk_time + signal_delay))
    if allow_bus:
        options.append(("bus", bus_time + traffic_delay + signal_delay))
    if allow_subway:
        options.append(("subway", subway_time + signal_delay))

    # choose best (min time)
    best = min(options, key=lambda x: x[1])
    best_mode, commute_minutes = best

    # weather penalty
    weather_pen = 0
    if weather.get("rain"):
        weather_pen = 5

    sched = ScheduleAgent(target_time, prep_minutes)
    wake_dt = sched.decide_wakeup(commute_minutes, wait_eta=None, weather_penalty=weather_pen)

    # OSRM route coords
    try:
        mode_osrm = "walking" if best_mode=="walk" else "driving"
        route_coords = ra.get_osrm_route_coords(start_coord, end_coord, mode=mode_osrm)
    except Exception:
        route_coords = []

    # UI: 결과표시
    st.subheader("결과 요약")
    st.write(f"권장 이동수단: **{best_mode}**")
    st.write(f"예상 통학 소요 (분): **{commute_minutes}**")
    st.write(f"권장 기상 시간: **{wake_dt.strftime('%Y-%m-%d %H:%M')}**")
    st.write(f"날씨: {'비/눈 가능' if weather.get('rain') else '맑음/비없음'}")
    st.write(f"도로 지연(가중치): {traffic_delay}분, 신호 대기(가중치): {signal_delay}분")

    # 지도 그리기
    st.subheader("경로 지도")
    mid = ((start_coord[0]+end_coord[0])/2, (start_coord[1]+end_coord[1])/2)
    m = folium.Map(location=mid, zoom_start=13)
    folium.Marker(location=start_coord, tooltip="출발", popup=start_addr, icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(location=end_coord, tooltip="도착", popup=end_addr, icon=folium.Icon(color="red")).add_to(m)
    if route_coords:
        folium.PolyLine(route_coords, weight=5, opacity=0.8).add_to(m)
    for lat,lon,wt in crossing_points:
        folium.CircleMarker(location=(lat,lon), radius=5, color="orange", popup=f"횡단보도 대기(초): {wt}").add_to(m)
    st_folium(m, width=900, height=450)

    # 브라우저 알림 스케줄링: JS를 통해 Notification API 사용
    # 계산: wake_dt -> delay ms
    now = datetime.now()
    delay_ms = max(0, int((wake_dt - now).total_seconds() * 1000))
    # safety cap: if delay too large (>7 days), do immediate
    if delay_ms > 7*24*3600*1000:
        delay_ms = 0

    st.markdown("---")
    st.subheader("알람 테스트 (브라우저 Notification)")
    st.write("브라우저의 알림 권한을 허용해 주세요. 알림은 이 탭에서만 동작합니다.")

    # 버튼: 즉시 알림(디버그) + 예약 알림
    col1, col2 = st.columns(2)
    if col1.button("즉시 알림"):
        st.markdown("""
            <script>
                alert("🛎 즉시 알림: 알람 동작 확인용!");
            </script>
        """, unsafe_allow_html=True)

    if col2.button("예약 알림 등록"):
        # inject JS: 요청 권한 -> setTimeout -> Notification or alert
        js = f"""
        <script>
        (async function() {{
            function notifyNow(){
                if (window.Notification && Notification.permission === "granted") {{
                    new Notification("Smart Commute", {{ body: "알람: {wake_dt.strftime('%Y-%m-%d %H:%M')}에 기상하세요!" }});
                }} else {{
                    alert("알람: {wake_dt.strftime('%Y-%m-%d %H:%M')}에 기상하세요!");
                }}
            }}
            if (!("Notification" in window)) {{
                alert("이 브라우저는 Notification을 지원하지 않습니다.");
                return;
            }}
            if (Notification.permission === "granted") {{
                setTimeout(notifyNow, {delay_ms});
                alert("예약 알림이 등록되었습니다. 알림은 이 탭에서 동작합니다.");
            }} else if (Notification.permission !== "denied") {{
                let p = await Notification.requestPermission();
                if (p === "granted") {{
                    setTimeout(notifyNow, {delay_ms});
                    alert("알림 권한 승인됨. 예약 알림 등록되었습니다.");
                }} else {{
                    alert("알림 권한을 거부하셨습니다. 즉시 알림으로 확인하세요.");
                }}
            }} else {{
                alert("알림 권한이 차단되어 있습니다. 브라우저 설정에서 허용해주세요.");
            }}
        }})();
        </script>
        """
        st.components.v1.html(js, height=10)

    st.success("계산이 완료되었습니다. 필요하면 '예약 알림 등록' 버튼으로 브라우저 알림을 등록하세요.")
    