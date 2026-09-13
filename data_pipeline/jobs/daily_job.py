from data_pipeline.ingestion.market_data import fetch_market_data

def run_daily_job():
    data = fetch_market_data()
    return {"rows": len(data), "status": "completed"}

if __name__ == "__main__":
    print(run_daily_job())
