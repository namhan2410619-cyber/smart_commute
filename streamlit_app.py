# streamlit_app.py
from datetime import datetime, timedelta
import streamlit as st
from utils.map_utils import geocode
from agents.data_agent import DataAgent
from agents.route_agent import RouteAgent
from agents.history_agent import HistoryAgent
from agents.schedule_agent import ScheduleAgent
from agents.iot_agent import send_browser_alarm
from streamlit_folium import st_folium
import folium

# =========================
# Streamlit state init
# =========================
if "result" not in st.session_state:
    st.session_state["result"] = None

if "progressive_js" not in st.session_state:
    st.session_state["progressive_js"] = None

# =========================
# Page config
# =========================
st.set_page_config(page_title="Smart Commute", layout="wide")
st.title("Smart Commute — 통합 시스템")

# =========================
# Agents
# =========================
da = DataAgent()
ra = RouteAgent()
ha = HistoryAgent()

# =========================
# Sidebar (입력)
# =========================
st.sidebar.header("설정")

start_addr = st.sidebar.text_input("출발지 주소", "서울특별시 중구 세종대로 110")
end_addr = st.sidebar.text_input("목적지 주소", "서울특별시 강남구 역삼동")
target_time = st.sidebar.text_input("도착 목표 시간 (HH:MM)", "08:40")

prep_minutes = st.sidebar.slider("준비 시간 (분)", 5, 90, 30)
safety_margin = st.sidebar.slider("안전 여유 (분)", 0, 20, 5)

allow_walk = st.sidebar.checkbox("도보", True)
allow_bus = st.sidebar.checkbox("버스", True)
allow_subway = st.sidebar.checkbox("지하철", True)

use_ml_correction = st.sidebar.checkbox("히스토리 보정 사용", True)
progressive_levels = st.sidebar.multiselect(
    "점진 알람 단계 (분 전)",
    [30, 10, 0],
    default=[30, 10, 0]
)

# =========================
# 계산 버튼 (계산 + 저장만!)
# =========================
if st.button("🚀 계산 시작"):
    try:
        start_coord = geocode(start_addr)
        end_coord = geocode(end_addr)
    except Exception as e:
        st.error(f"주소 변환 실패: {e}")
        st.stop()

    weather = da.get_weather(start_coord)
    crossings = da.get_crossings_info(start_coord, end_coord)
    signal_penalty = da.traffic_light_penalty_minutes(crossings)
    traffic_delay = da.get_traffic_delay(start_coord, end_coord)

    options = []
    if allow_walk:
        options.append(("walk", ra.estimate_walk_minutes(start_coord, end_coord) + signal_penalty))
    if allow_bus:
        options.append(("bus", ra.estimate_bus_minutes(start_coord, end_coord) + traffic_delay + signal_penalty))
    if allow_subway:
        options.append(("subway", ra.estimate_subway_minutes(start_coord, end_coord) + signal_penalty))

    if not options:
        st.error("이동수단을 선택하세요.")
        st.stop()

    best_mode, base_minutes = min(options, key=lambda x: x[1])

    mean_err, std_err = (0, 0)
    if use_ml_correction:
        mean_err, std_err = ha.predict_correction(f"{start_addr}|{end_addr}", best_mode)

    final_minutes = max(1, int(base_minutes + mean_err))

    weather_pen = 5 if weather.get("rain") else 0

    sa = ScheduleAgent(target_time, prep_minutes, safety_margin)
    wake_dt = sa.compute_wakeup_dt(
        final_minutes,
        weather_penalty=weather_pen
    )

    coords = ra.get_osrm_coords(
        start_coord,
        end_coord,
        mode="walking" if best_mode == "walk" else "driving"
    )

    # ✅ 결과 저장 (핵심)
    st.session_state["result"] = {
        "best_mode": best_mode,
        "base_minutes": base_minutes,
        "final_minutes": final_minutes,
        "wake_dt": wake_dt,
        "weather": weather,
        "traffic_delay": traffic_delay,
        "signal_penalty": signal_penalty,
        "mean_err": mean_err,
        "std_err": std_err,
        "start_coord": start_coord,
        "end_coord": end_coord,
        "coords": coords,
        "crossings": crossings,
        "progressive_levels": progressive_levels
    }

# =========================
# 결과 출력 (항상 유지됨)
# =========================
if st.session_state["result"]:
    r = st.session_state["result"]

    st.success("✅ 계산 완료")
    st.write("**권장 이동수단:**", r["best_mode"])
    st.write("기본 ETA:", r["base_minutes"], "분")
    st.write("보정 ETA:", r["final_minutes"], "분")
    st.write("권장 기상 시간:", r["wake_dt"].strftime("%Y-%m-%d %H:%M"))

    if use_ml_correction:
        st.info(f"히스토리 오차: 평균 {r['mean_err']:+.1f}분 / 표준편차 {r['std_err']:.1f}분")

    # =========================
    # 지도 (사라지지 않음)
    # =========================
    mid = (
        (r["start_coord"][0] + r["end_coord"][0]) / 2,
        (r["start_coord"][1] + r["end_coord"][1]) / 2
    )

    m = folium.Map(location=mid, zoom_start=13)
    folium.Marker(r["start_coord"], popup="출발지", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(r["end_coord"], popup="도착지", icon=folium.Icon(color="red")).add_to(m)

    if r["coords"]:
        folium.PolyLine(r["coords"], color="blue", weight=5).add_to(m)

    for lat, lon, wt in r["crossings"]:
        folium.CircleMarker(
            location=(lat, lon),
            radius=4,
            color="orange",
            popup=f"신호 대기 {wt}초"
        ).add_to(m)

    st_folium(m, width=700, height=450)

    # =========================
    # 알람
    # =========================
    if st.button("🔔 점진 알람 등록"):
        now = datetime.now()
        js_blocks = []

        for lvl in sorted(r["progressive_levels"], reverse=True):
            alarm_time = r["wake_dt"] - timedelta(minutes=lvl)
            delay_ms = max(0, int((alarm_time - now).total_seconds() * 1000))
            msg = f"{lvl}분 전 알림 (기상 {r['wake_dt'].strftime('%H:%M')})"

            js_blocks.append(f"""
            setTimeout(() => {{
                if (Notification.permission === "granted") {{
                    new Notification("Smart Commute", {{ body: "{msg}" }});
                }} else {{
                    alert("{msg}");
                }}
            }}, {delay_ms});
            """)

        js = "<script>" + "".join(js_blocks) + "</script>"
        st.components.v1.html(js, height=0)
        st.success("알람 등록 완료 (탭 유지 필요)")
