
# agents/history_agent.py
import sqlite3
import os
from datetime import datetime
import numpy as np
from sklearn.linear_model import LinearRegression

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "eta_history.db")

class HistoryAgent:
    def __init__(self, dbpath=DB_PATH):
        self.dbpath = dbpath
        self._ensure_db()

    def _ensure_db(self):
        conn = sqlite3.connect(self.dbpath)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS eta_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_key TEXT,
            mode TEXT,
            predicted INTEGER,
            actual INTEGER,
            timestamp TEXT
        )
        """)
        conn.commit()
        conn.close()

    def add_record(self, route_key, mode, predicted_minutes, actual_minutes):
        conn = sqlite3.connect(self.dbpath)
        c = conn.cursor()
        c.execute("INSERT INTO eta_history(route_key, mode, predicted, actual, timestamp) VALUES (?, ?, ?, ?, ?)",
                  (route_key, mode, int(predicted_minutes), int(actual_minutes), datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()

    def summarize(self, route_key, mode, limit=200):
        conn = sqlite3.connect(self.dbpath)
        c = conn.cursor()
        c.execute("SELECT predicted, actual FROM eta_history WHERE route_key=? AND mode=? ORDER BY id DESC LIMIT ?", (route_key, mode, limit))
        rows = c.fetchall()
        conn.close()
        if not rows:
            return None
        preds = np.array([r[0] for r in rows])
        acts = np.array([r[1] for r in rows])
        diffs = acts - preds
        return {"count": len(rows), "mean_error": float(diffs.mean()), "std_error": float(diffs.std())}

    def predict_correction(self, route_key, mode):
        """
        Return (mean_error, std_error) — positive means actual > predicted => add time
        """
        s = self.summarize(route_key, mode)
        if not s:
            return 0.0, 0.0
        return s["mean_error"], s["std_error"]

    def train_simple_model(self, route_key, mode):
        """
        (optional) train a linear regression: actual ~ predicted
        returns (slope, intercept) if trained else None
        """
        conn = sqlite3.connect(self.dbpath)
        c = conn.cursor()
        c.execute("SELECT predicted, actual FROM eta_history WHERE route_key=? AND mode=?", (route_key, mode))
        rows = c.fetchall()
        conn.close()
        if len(rows) < 10:
            return None
        X = [[r[0]] for r in rows]
        y = [r[1] for r in rows]
        model = LinearRegression().fit(X, y)
        return float(model.coef_[0]), float(model.intercept_)
