"""SolarCast - Solar Power Generation Prediction System (Flask backend).

Run:  python app.py   then open  http://127.0.0.1:5000
"""
import csv
import io
import json
import os
import random
import threading
from collections import defaultdict
from datetime import datetime, timedelta

import joblib
import numpy as np
import pandas as pd
from flask import Flask, Response, jsonify, request, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE, "model.pkl")
HISTORY_PATH = os.path.join(BASE, "history.json")

# The HTML/CSS/JS files live in the project folder, so serve them from there.
app = Flask(__name__, static_folder=BASE, static_url_path="")
lock = threading.Lock()

PANEL_AREA_M2 = 28.0     # simulated array area used for efficiency
CO2_KG_PER_KWH = 0.82    # approx. Indian grid emission factor
KG_CO2_PER_TREE_YEAR = 21

if not os.path.exists(MODEL_PATH):
    import train
    train.train()
bundle = joblib.load(MODEL_PATH)
model, FEATURES = bundle["model"], bundle["features"]
CAPACITY = bundle.get("capacity_kw", 5.0)


# ---------- helpers ----------
def read_history():
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def write_history(rows):
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f)


def num(data, key, lo, hi, default=None):
    if key not in data or data[key] in ("", None):
        if default is not None:
            return default
        raise ValueError(f"Please enter {key.replace('_', ' ')}.")
    try:
        v = float(data[key])
    except (TypeError, ValueError):
        raise ValueError(f"{key.replace('_', ' ')} must be a number.")
    if not lo <= v <= hi:
        raise ValueError(f"{key.replace('_', ' ')} must be between {lo} and {hi}.")
    return v


def predict_power(t, h, g, w):
    x = pd.DataFrame([[t, h, g, w]], columns=FEATURES)
    return float(np.clip(model.predict(x)[0], 0, CAPACITY))


def build_result(t, h, g, w, sun_hours, tariff):
    power = predict_power(t, h, g, w)
    energy = power * sun_hours
    eff = (power * 1000 / (PANEL_AREA_M2 * g) * 100) if g > 0 else 0.0
    co2 = energy * CO2_KG_PER_KWH

    # typical daily irradiation bell curve (6:00 - 18:00) scaled to the entered irradiation
    hourly = []
    for hr in range(6, 19):
        shape = max(0.0, np.sin(np.pi * (hr - 6) / 12))
        gi = g * shape / max(np.sin(np.pi * 6 / 12), 1e-9)  # peak at 12:00 == g
        hourly.append({"hour": f"{hr:02d}:00", "power_kw": round(predict_power(t, h, gi, w), 3)})
    best = sorted(hourly, key=lambda r: r["power_kw"], reverse=True)[:3]
    best_hours = sorted(b["hour"] for b in best)

    alerts = []
    if power < 0.3 * CAPACITY:
        alerts.append({"level": "warn", "text": "Low solar generation expected. Consider shifting heavy loads to another time."})
    if t >= 40:
        alerts.append({"level": "danger", "text": "High temperature warning: panel efficiency drops as cells get hotter."})
    if h >= 85:
        alerts.append({"level": "warn", "text": "Very high humidity may reduce output (haze / cloud cover)."})
    if not alerts:
        alerts.append({"level": "ok", "text": "Conditions look good for solar generation."})

    ratio = power / CAPACITY
    perf = "Excellent" if ratio >= 0.7 else "Good" if ratio >= 0.45 else "Moderate" if ratio >= 0.25 else "Poor"
    if g < 300:
        rec = "Irradiation is low. Schedule heavy appliances for sunnier hours or use the grid."
    elif t >= 38:
        rec = "Keep panels clean and ventilated; heat is cutting some efficiency."
    else:
        rec = "Run high-load appliances (pump, washing machine, AC) around midday to use solar directly."

    return {
        "power_kw": round(power, 3),
        "energy_kwh": round(energy, 2),
        "efficiency_pct": round(eff, 2),
        "capacity_kw": CAPACITY,
        "savings": round(energy * tariff, 2),
        "co2_kg": round(co2, 2),
        "trees_equiv_year": round(co2 * 365 / KG_CO2_PER_TREE_YEAR, 1),
        "performance": perf,
        "recommendation": rec,
        "best_hours": f"{best_hours[0]} - {best_hours[-1]}",
        "hourly": hourly,
        "alerts": alerts,
    }


# ---------- pages ----------
@app.route("/")
def home():
    return send_from_directory(BASE, "index.html")


@app.route("/dashboard")
def dashboard():
    return send_from_directory(BASE, "dashboard.html")


@app.route("/about")
def about():
    return send_from_directory(BASE, "about.html")


# ---------- API ----------
@app.route("/api/predict", methods=["POST"])
def api_predict():
    data = request.get_json(silent=True) or {}
    try:
        t = num(data, "temperature", -20, 70)
        h = num(data, "humidity", 0, 100)
        g = num(data, "irradiation", 0, 1500)
        w = num(data, "wind_speed", 0, 60)
        sun = num(data, "sun_hours", 0, 14, 6)
        tariff = num(data, "tariff", 0, 1000, 8)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    res = build_result(t, h, g, w, sun, tariff)
    entry = {
        "id": int(datetime.now().timestamp() * 1000),
        "time": datetime.now().isoformat(timespec="seconds"),
        "temperature": t, "humidity": h, "irradiation": g, "wind_speed": w,
        "sun_hours": sun, "tariff": tariff,
        "power_kw": res["power_kw"], "energy_kwh": res["energy_kwh"],
        "efficiency_pct": res["efficiency_pct"], "savings": res["savings"],
        "co2_kg": res["co2_kg"],
    }
    with lock:
        rows = read_history()
        rows.append(entry)
        write_history(rows[-500:])
    return jsonify(res)


@app.route("/api/history", methods=["GET", "DELETE"])
def api_history():
    with lock:
        if request.method == "DELETE":
            write_history([])
            return jsonify({"ok": True})
        return jsonify(list(reversed(read_history())))


@app.route("/api/history/sample", methods=["POST"])
def api_sample():
    """Add 30 days of sample predictions so charts/analytics can be explored."""
    rnd = random.Random()
    now = datetime.now()
    rows = []
    for d in range(29, -1, -1):
        day = now - timedelta(days=d)
        for k in range(2):
            t = rnd.uniform(24, 41); h = rnd.uniform(25, 85)
            g = rnd.uniform(250, 950); w = rnd.uniform(0.5, 8)
            p = predict_power(t, h, g, w)
            eff = p * 1000 / (PANEL_AREA_M2 * g) * 100
            rows.append({
                "id": int(day.timestamp() * 1000) + k,
                "time": day.replace(hour=11 + 3 * k, minute=0, second=0, microsecond=0).isoformat(timespec="seconds"),
                "temperature": round(t, 1), "humidity": round(h, 1),
                "irradiation": round(g, 1), "wind_speed": round(w, 1),
                "sun_hours": 6, "tariff": 8, "power_kw": round(p, 3),
                "energy_kwh": round(p * 6, 2), "efficiency_pct": round(eff, 2),
                "savings": round(p * 6 * 8, 2), "co2_kg": round(p * 6 * CO2_KG_PER_KWH, 2),
            })
    with lock:
        existing = read_history()
        write_history((existing + rows)[-500:])
    return jsonify({"added": len(rows)})


@app.route("/api/analytics")
def api_analytics():
    rows = read_history()
    per_day = defaultdict(list)
    for r in rows:
        per_day[r["time"][:10]].append(r["energy_kwh"])
    daily = {d: sum(v) / len(v) for d, v in per_day.items()}  # avg predicted daily energy

    weekly, monthly = defaultdict(float), defaultdict(float)
    for d, e in daily.items():
        dt = datetime.strptime(d, "%Y-%m-%d")
        iso = dt.isocalendar()
        weekly[f"{iso[0]}-W{iso[1]:02d}"] += e
        monthly[dt.strftime("%Y-%m")] += e

    fmt = lambda dct, n: [{"label": k, "energy_kwh": round(dct[k], 2)} for k in sorted(dct)[-n:]]
    return jsonify({"daily": fmt(daily, 14), "weekly": fmt(weekly, 8), "monthly": fmt(monthly, 6)})


@app.route("/api/metrics")
def api_metrics():
    return jsonify({**bundle["metrics"], "compare": bundle["compare"]})


@app.route("/api/report.csv")
def api_report():
    rows = read_history()
    buf = io.StringIO()
    cols = ["time", "temperature", "humidity", "irradiation", "wind_speed", "sun_hours",
            "tariff", "power_kw", "energy_kwh", "efficiency_pct", "savings", "co2_kg"]
    wr = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    wr.writeheader()
    wr.writerows(rows)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=solar_prediction_report.csv"})


@app.errorhandler(Exception)
def on_error(e):
    # Always answer with JSON for API calls (avoids "Unexpected end of JSON" in the browser)
    if request.path.startswith("/api/"):
        return jsonify({"error": f"Server error: {e}"}), 500
    raise e


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
