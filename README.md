# Sector Rotation Screener

Starter project for a sector rotation and market screening system.

## Windows CMD setup

```cmd
cd C:\Development\sector_rotation_screener
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
python -m uvicorn backend.main:app --reload
```

Open:
- http://127.0.0.1:8000
- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/api/v1/health
- http://127.0.0.1:8000/api/v1/sectors

## Notes

This is a local starter implementation. It currently uses sample sector data.
An external market-data provider will be connected in a later phase.
