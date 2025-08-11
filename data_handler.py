import pandas as pd
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

def load_csv(name):
    path = os.path.join(DATA_DIR, name)
    for enc in ["utf-8", "utf-8-sig", "cp1251"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    return None

def get_today_stats():
    df = load_csv("data_bot.csv")
    if df is None:
        return "Файл data_bot.csv не найден."
    return df.to_string(index=False)

def get_goals():
    df = load_csv("Power.Bi.MP-2.csv")
    if df is None:
        return "Файл Power.Bi.MP-2.csv не найден."
    return df.head(10).to_string(index=False)

def get_dashboard():
    df = load_csv("DashBoard.csv")
    if df is None:
        return "Файл DashBoard.csv не найден."
    return df.head(10).to_string(index=False)
