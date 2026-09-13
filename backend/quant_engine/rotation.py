import pandas as pd

SAMPLE_SECTORS = [
    {"sector": "NIFTY IT", "relative_strength": 82.5, "momentum": 76.2},
    {"sector": "NIFTY Auto", "relative_strength": 74.1, "momentum": 71.8},
    {"sector": "NIFTY Bank", "relative_strength": 68.4, "momentum": 65.7},
    {"sector": "NIFTY Pharma", "relative_strength": 61.2, "momentum": 59.3},
    {"sector": "NIFTY FMCG", "relative_strength": 52.8, "momentum": 48.9},
    {"sector": "NIFTY Metal", "relative_strength": 45.6, "momentum": 43.2},
    {"sector": "NIFTY Realty", "relative_strength": 39.7, "momentum": 36.4},
]

def calculate_rotation_scores():
    df = pd.DataFrame(SAMPLE_SECTORS)
    df["score"] = (df["relative_strength"] * 0.6) + (df["momentum"] * 0.4)
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    df["trend"] = df["score"].apply(
        lambda x: "strong" if x >= 70 else "positive" if x >= 55 else "weak"
    )
    return df[
        ["sector", "relative_strength", "momentum", "trend", "rank"]
    ].to_dict(orient="records")
