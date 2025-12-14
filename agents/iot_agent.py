# agents/iot_agent.py
import streamlit as st

def send_browser_alarm(title: str, message: str):
    """
    Inject JS to request permission (if needed) and show a notification immediately.
    """
    # Use f-string but escape JS braces with double {{ }}
    js = f"""
    <script>
    (function() {{
        function notify() {{
            try {{
                new Notification("{title}", {{ body: "{message}" }});
            }} catch(e) {{
                alert("{title}\\n{message}");
            }}
        }}
        if (window.Notification && Notification.permission === "granted") {{
            notify();
        }} else if (window.Notification && Notification.permission !== "denied") {{
            Notification.requestPermission().then(function(permission) {{
                if (permission === "granted") {{
                    notify();
                }} else {{
                    alert("{title}\\n{message}");
                }}
            }});
        }} else {{
            alert("{title}\\n{message}");
        }}
    }})();
    </script>
    """
    st.components.v1.html(js, height=0)
