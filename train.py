"""Train the solar power prediction model.

Run:  python train.py
Creates dataset.csv (if missing) and model.pkl.
"""
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

BASE = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(BASE, "dataset.csv")
MODEL = os.path.join(BASE, "model.pkl")
FEATURES = ["temperature", "humidity", "irradiation", "wind_speed"]
TARGET = "power_kw"
CAPACITY_KW = 5.0  # simulated rooftop system


def make_dataset(n=3000, seed=42):
    """Synthetic data based on a simple PV physics model + noise.
    Replace dataset.csv with real measurements to train on your own site."""
    rng = np.random.default_rng(seed)
    irr = np.clip(rng.normal(520, 280, n), 0, 1100)
    temp = np.clip(rng.normal(30, 7, n) + irr * 0.004, 5, 48)
    hum = np.clip(rng.normal(55, 20, n) - irr * 0.01, 10, 100)
    wind = np.clip(rng.gamma(2.2, 1.6, n), 0, 18)
    cell = temp + 0.025 * irr - 1.2 * wind
    p = CAPACITY_KW * (irr / 1000) * (1 - 0.0042 * (cell - 25)) * (1 - 0.0006 * hum)
    p = p + rng.normal(0, 0.06, n)
    p = np.clip(p, 0, CAPACITY_KW)
    df = pd.DataFrame({"temperature": temp.round(1), "humidity": hum.round(1),
                       "irradiation": irr.round(1), "wind_speed": wind.round(2),
                       "power_kw": p.round(3)})
    df.to_csv(DATASET, index=False)
    return df


def train():
    df = pd.read_csv(DATASET) if os.path.exists(DATASET) else make_dataset()
    X, y = df[FEATURES], df[TARGET]
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)

    candidates = {
        "Linear Regression": LinearRegression(),
        "Random Forest": RandomForestRegressor(n_estimators=80, min_samples_leaf=4,
                                               random_state=42, n_jobs=-1),
    }
    best_name, best_model, best_r2, scores = None, None, -1e9, {}
    for name, m in candidates.items():
        m.fit(Xtr, ytr)
        pred = m.predict(Xte)
        r2 = r2_score(yte, pred)
        scores[name] = round(float(r2), 4)
        print(f"{name}: R2={r2:.4f}")
        if r2 > best_r2:
            best_name, best_model, best_r2 = name, m, r2

    pred = np.clip(best_model.predict(Xte), 0, None)
    metrics = {
        "model": best_name,
        "r2": round(float(r2_score(yte, pred)), 4),
        "mae": round(float(mean_absolute_error(yte, pred)), 4),
        "rmse": round(float(np.sqrt(mean_squared_error(yte, pred))), 4),
        "train_rows": int(len(Xtr)), "test_rows": int(len(Xte)),
        "all_models": scores,
    }
    compare = [{"actual": round(float(a), 3), "predicted": round(float(p), 3)}
               for a, p in list(zip(yte.values, pred))[:40]]
    joblib.dump({"model": best_model, "features": FEATURES, "metrics": metrics,
                 "compare": compare, "capacity_kw": CAPACITY_KW}, MODEL, compress=3)
    print("Saved model.pkl ->", metrics)


if __name__ == "__main__":
    train()
