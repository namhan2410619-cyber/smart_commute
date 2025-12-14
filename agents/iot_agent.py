import streamlit as st

def send_browser_alarm(title: str, message: str):
    """
    Streamlit에서 브라우저 알람을 띄우는 함수
    - title: 알람 제목
    - message: 알람 내용
    """
    js_code = f"""
    <script>
    if (window.Notification && Notification.permission === "granted") {{
        new Notification("{title}", {{ body: "{message}" }});
    }} else if (window.Notification && Notification.permission !== "denied") {{
        Notification.requestPermission().then(function(permission) {{
            if(permission === "granted") {{
                new Notification("{title}", {{ body: "{message}" }});
            }}
        }});
    }}
    </script>
    """
    st.components.v1.html(js_code)
