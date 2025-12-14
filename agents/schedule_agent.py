# agents/schedule_agent.py
from datetime import datetime, timedelta

class ScheduleAgent:
    def __init__(self, target_time_str="08:40", prep_minutes=30, safety_margin=5):
        self.target_time_str = target_time_str
        self.prep_minutes = int(prep_minutes)
        self.safety_margin = int(safety_margin)

    def compute_wakeup_dt(self, travel_minutes, wait_eta=0, weather_penalty=0, extra_margin=0):
        total = int(travel_minutes) + int(wait_eta) + int(weather_penalty) + int(self.prep_minutes) + int(self.safety_margin) + int(extra_margin)
        today = datetime.now().date()
        sh, sm = map(int, self.target_time_str.split(":"))
        school_dt = datetime.combine(today, datetime.min.time()).replace(hour=sh, minute=sm)
        wake_dt = school_dt - timedelta(minutes=total)
        return wake_dt

    def dynamic_update_interval_seconds(self, wake_dt):
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
