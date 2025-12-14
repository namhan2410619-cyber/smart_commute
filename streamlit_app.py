# streamlit_app.py
import streamlit as st
from utils.map_utils import geocode
from agents.data_agent import DataAgent
from agents.route_agent import RouteAgent
from agents.history_agent import HistoryAgent
from agents.schedule_agent import ScheduleAgent
from agents.iot_agent import send_browser_alarm
from datetime import datetime
from streamlit_folium import st_folium
import folium
import math
import time

st.set_page_config(page_title="Smart Commute (통합)", layout="wide")
st.title("Smart Commute — 통합 (히스토리 보정 / 신호등 / 점진 알람 포함)")

# init agents
da = DataAgent()
ra = RouteAgent()
ha = HistoryAgent()
# UI: left panel input
st.sidebar.header("설정")
start_addr = st.sidebar.text_input("출발지 주소", "서울특별시 중구 세종대로 110")
end_addr = st.sidebar.text_input("목적지 주소", "서울특별시 강남구 역삼동")
target_time = st.sidebar.text_input("도착(등교) 목표 시간 (HH:MM)", "08:40")
prep_minutes = st.sidebar.slider("준비 시간 (분)", 5, 90, 30)
safety_margin = st.sidebar.slider("기본 안전여유(분)", 0, 20, 5)
allow_walk = st.sidebar.checkbox("도보 포함", value=True)
allow_bus = st.sidebar.checkbox("버스 포함", value=True)
allow_subway = st.sidebar.checkbox("지하철 포함", value=True)
use_ml_correction = st.sidebar.checkbox("히스토리 기반 보정 사용", value=True)
progressive_levels = st.sidebar.multiselect("점진 알람 단계 (분 전)", [30, 10, 0], default=[30,10,0])

# main column
col1, col2 = st.columns([1,2])

with col1:
    if st.button("계산 시작"):
        # 1) geocode
        try:
            start_coord = geocode(start_addr)
            end_coord = geocode(end_addr)
        except Exception as e:
            st.error(f"주소 변환 실패: {e}")
            st.stop()

        # 2) realtime data
        weather = da.get_weather(start_coord)  # {'rain': bool}
        crossings = da.get_crossings_info(start_coord, end_coord)
        signal_penalty_min = da.traffic_light_penalty_minutes(crossings)
        traffic_delay_min = da.get_traffic_delay(start_coord, end_coord)

        # 3) baseline ETA estimates
        options = []
        if allow_walk:
            walk_min = ra.estimate_walk_minutes(start_coord, end_coord)
            # add signal penalty for walk
            walk_min_total = walk_min + signal_penalty_min
            options.append(("walk", walk_min_total))
        if allow_bus:
            bus_min = ra.estimate_bus_minutes(start_coord, end_coord)
            bus_min_total = bus_min + traffic_delay_min + signal_penalty_min
            options.append(("bus", bus_min_total))
        if allow_subway:
            subway_min = ra.estimate_subway_minutes(start_coord, end_coord)
            subway_min_total = subway_min + signal_penalty_min
            options.append(("subway", subway_min_total))

        if not options:
            st.error("이동수단을 하나 이상 선택하세요.")
            st.stop()

        # 4) choose best by ETA (this is simple; could be multi-criteria)
        best_mode, predicted_minutes = min(options, key=lambda x: x[1])

        # 5) history correction
        route_key = f"{start_addr}|{end_addr}"
        mean_err, std_err = 0.0, 0.0
        if use_ml_correction:
            mean_err, std_err = ha.predict_correction(route_key, best_mode)
            # apply mean error as correction (if positive -> actual longer than predicted)
            predicted_adj = max(1, int(predicted_minutes + mean_err))
        else:
            predicted_adj = int(predicted_minutes)

        # 6) weather penalty
        weather_pen = 0
        if weather.get("rain"):
            weather_pen += 5

        # 7) final commute minutes and wake calculation
        sa = ScheduleAgent(target_time, prep_minutes, safety_margin)
        wake_dt = sa.compute_wakeup_dt(predicted_adj, wait_eta=0, weather_penalty=weather_pen, extra_margin=0)

        # 8) save history: here we simulate actual==predicted for demo, but in real use call ha.add_record after trip with actual
        # ha.add_record(route_key, best_mode, predicted_minutes, actual_minutes)

        # 9) show summary
        st.success("계산 완료")
        st.write("권장 이동수단:", best_mode)
        st.write("예상 소요(기본):", predicted_minutes, "분")
        if use_ml_correction:
            st.write(f"히스토리 평균 오차: {mean_err:+.1f}분 (표준편차 {std_err:.1f}분)")
            st.write("보정 후 ETA:", predicted_adj, "분")
        st.write(f"날씨(비 여부): {weather.get('rain')}")
        st.write(f"도로 지연 가중치: {traffic_delay_min}분, 횡단보도/신호 대기: {signal_penalty_min}분")
        st.write("권장 기상 시간:", wake_dt.strftime("%Y-%m-%d %H:%M"))

        # 10) map
        with st.spinner("지도 생성 중..."):
            coords = ra.get_osrm_coords(start_coord, end_coord, mode="walking" if best_mode=="walk" else "driving")
            mid = ((start_coord[0]+end_coord[0])/2, (start_coord[1]+end_coord[1])/2)
            m = folium.Map(location=mid, zoom_start=13)
            folium.Marker(location=start_coord, popup="출발지", icon=folium.Icon(color="green")).add_to(m)
            folium.Marker(location=end_coord, popup="도착지", icon=folium.Icon(color="red")).add_to(m)
            if coords:
                folium.PolyLine(coords, weight=5, color="blue", opacity=0.8).add_to(m)
            # crossings markers
            for lat,lon,wt in crossings:
                folium.CircleMarker(location=(lat,lon), radius=4, color="orange", popup=f"횡단보도 대기(초):{wt}").add_to(m)
            st_folium(m, width=700, height=450)

        # 11) show confidence interval
        if use_ml_correction and (abs(mean_err) > 0 or std_err > 0):
            st.info(f"ETA 신뢰구간: 보정 ETA ± {std_err:.1f} 분 (과거 데이터 기반)")

        # 12) scheduling: prepare progressive alarms
        # compute delays in ms from now
        now = datetime.now()
        def minutes_until(dt):
            return max(0, int((dt - datetime.now()).total_seconds()/60))
        # times (in ms) for each progressive level
        delays_ms = []
        for lvl in sorted(progressive_levels, reverse=True):
            # lvl is minutes before wake_dt -> alarm time = wake_dt - lvl
            alarm_time = wake_dt - timedelta(minutes=lvl)
            delay_ms = int(max(0, (alarm_time - now).total_seconds()) * 1000)
            delays_ms.append((lvl, delay_ms))

        # 13) inject JS to register progressive alarms (setTimeout)
        # careful with braces in f-strings; use double braces to output single braces in JS
        # build JS string
        progressive_js_parts = []
        for lvl, dms in delays_ms:
            msg = f"알림: {wake_dt.strftime('%H:%M')} - {lvl}분 전 알림입니다."
            # create JS for this level
            part = f"""
            (function() {{
                function notify_{lvl}() {{
                    try {{
                        new Notification("Smart Commute", {{ body: "{msg}" }});
                    }} catch(e) {{
                        alert("{msg}");
                    }}
                }}
                if (Notification && Notification.permission === "granted") {{
                    setTimeout(notify_{lvl}, {dms});
                }} else if (Notification && Notification.permission !== "denied") {{
                    Notification.requestPermission().then(function(p) {{
                        if (p === "granted") {{
                            setTimeout(notify_{lvl}, {dms});
                        }} else {{
                            // fallback: setTimeout to alert (can't schedule if permission denied for Notification)
                            setTimeout(function() {{ alert("{msg}"); }}, {dms});
                        }}
                    }});
                }} else {{
                    setTimeout(function() {{ alert("{msg}"); }}, {dms});
                }}
            }})();
            """
            progressive_js_parts.append(part)

        progressive_js = "<script>\n" + "\n".join(progressive_js_parts) + "\n</script>"

        st.markdown("---")
        st.subheader("알람 (점진 알림) 등록")
        st.write("브라우저의 알림 권한을 허용해 주세요. 알림은 이 브라우저 탭에서 동작합니다.")
        if st.button("점진 알림 등록"):
            # inject JS
            st.components.v1.html(progressive_js, height=10)
            st.success("점진 알림(등록됨). 탭을 닫지 마세요.")

        # small helper: immediate test
        if st.button("즉시 알람 테스트"):
            send_browser_alarm("Smart Commute 테스트", f"즉시 알림: 권장 기상 시간 {wake_dt.strftime('%H:%M')}")
