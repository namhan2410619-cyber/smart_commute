# agents/schedule_agent.py
from datetime import datetime, timedelta

class ScheduleAgent:
    def __init__(self, target_time_str="08:40", prep_minutes=30):
        self.target_time_str = target_time_str
        self.prep_minutes = int(prep_minutes)

    def decide_wakeup(self, travel_minutes, wait_eta=None, weather_penalty=0):
        wait = 0
        if wait_eta and wait_eta>0:
            wait = int(wait_eta)
        total = travel_minutes + wait + weather_penalty + self.prep_minutes
        today = datetime.now().date()
        sh, sm = map(int, self.target_time_str.split(":"))
        school_dt = datetime.combine(today, datetime.min.time()).replace(hour=sh, minute=sm)
        wake_dt = school_dt - timedelta(minutes=total)
        return wake_dt

    def dynamic_update_interval(self, wake_dt):
        # 남은 시간에 따라 갱신 주기(초)
        from datetime import datetime
        now = datetime.now()
        remaining = (wake_dt - now).total_seconds()
        if remaining <= 0:
            return 5
        if remaining < 60*10:
            return 30
        if remaining < 60*60:
            return 60
        if remaining < 60*60*3:
            return 300
        return 1800
