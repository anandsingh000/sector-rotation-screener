"""
AI Market Agent: wraps NVIDIA's hosted NIM inference API (OpenAI-compatible
chat completions at https://integrate.api.nvidia.com/v1/chat/completions)
to turn the Market Scanner's numbers into a plain-language Hinglish
summary of which stocks stand out on volume and cash flow.

Design principle: the STOCK SELECTION itself is always deterministic --
built from screener.scanner's already-computed, auditable numbers
(volume_ratio, cash_flow_trend). The LLM never picks stocks or invents
numbers; it only narrates a data table it's given. If the API call fails
for any reason (bad/missing key, network, rate limit), the deterministic
table still stands on its own -- the LLM layer is additive, not load-bearing.
"""

from __future__ import annotations

import pandas as pd
import requests

NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL = "meta/llama-3.1-70b-instruct"

SYSTEM_PROMPT = (
    "You are a market-data narrator for an Indian retail investor. You will be given a "
    "small table of NSE/BSE stocks with volume and cash-flow signals that were already "
    "computed by deterministic code -- you do not calculate or invent any numbers "
    "yourself. Write a concise Hinglish (Hindi+English mixed, Roman script) summary: "
    "group the standout names by what triggered them (volume surge, rising operating "
    "cash flow, or both), in 1 short line each, then a 2-3 line overall takeaway. Never "
    "give buy/sell recommendations, price targets, or investment advice -- describe what "
    "the data shows, not what to do about it. End with one line reminding the reader this "
    "is not investment advice."
)


def build_agent_candidates(
    scan_df: pd.DataFrame,
    min_volume_ratio: float = 1.5,
    top_n: int = 25,
) -> pd.DataFrame:
    """
    Deterministic shortlist: stocks with a volume surge (volume_ratio >=
    min_volume_ratio) and/or rising operating cash flow (only among rows
    that were actually fundamentals-scanned -- "Unknown" is never treated
    as "Rising"). This table is the actual answer to "which stocks have
    high volume or high cash flow" -- the LLM report below just narrates it.
    """
    if scan_df is None or scan_df.empty:
        return pd.DataFrame()

    df = scan_df.copy()
    has_volume_surge = df.get("volume_surge", False) == True  # noqa: E712
    has_rising_cf = df.get("cash_flow_trend", "") == "Rising"

    shortlisted = df[has_volume_surge | has_rising_cf].copy()
    if shortlisted.empty:
        return shortlisted

    shortlisted["_signal"] = shortlisted.apply(
        lambda r: ("Volume + Cash Flow" if r.get("volume_surge") and r.get("cash_flow_trend") == "Rising"
                    else "Volume Surge" if r.get("volume_surge")
                    else "Cash Flow Rising"),
        axis=1,
    )
    shortlisted = shortlisted.sort_values(
        by=["volume_ratio"], ascending=False, na_position="last"
    )
    return shortlisted.head(top_n)


def _format_candidates_for_prompt(candidates: pd.DataFrame) -> str:
    cols = ["symbol", "sector", "exchange", "_signal", "volume_ratio", "cash_flow_trend", "rsi", "ema_state", "valuation"]
    cols = [c for c in cols if c in candidates.columns]
    lines = []
    for _, r in candidates[cols].iterrows():
        parts = [f"{k}={r[k]}" for k in cols]
        lines.append(", ".join(str(p) for p in parts))
    return "\n".join(lines)


def call_nvidia_chat(
    api_key: str,
    user_content: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 900,
    timeout: int = 60,
) -> str:
    """
    One call to NVIDIA's OpenAI-compatible chat completions endpoint.
    Raises on failure (caller decides how to surface it) -- never silently
    returns fabricated text.
    """
    if not api_key or not api_key.strip():
        raise ValueError("NVIDIA API key khaali hai.")

    resp = requests.post(
        NVIDIA_API_URL,
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def generate_market_agent_report(
    candidates: pd.DataFrame,
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Returns {"ok": True, "text": ...} on success or {"ok": False, "error": ...}
    on failure -- never raises, so the UI can always render something.
    """
    if candidates is None or candidates.empty:
        return {"ok": False, "error": "Abhi koi stock shortlist mein nahi hai (koi volume surge ya rising cash flow nahi mila)."}

    table_text = _format_candidates_for_prompt(candidates)
    prompt = (
        f"Yahan {len(candidates)} NSE/BSE stocks hain jinmein volume surge aur/ya rising "
        f"operating cash flow dikha hai (data pehle se calculate ho chuka hai):\n\n{table_text}\n\n"
        "In sab ko group karke Hinglish mein summarize karo jaisa system prompt mein bataya gaya hai."
    )
    try:
        text = call_nvidia_chat(api_key, prompt, model=model)
        return {"ok": True, "text": text}
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        return {"ok": False, "error": f"NVIDIA API error (HTTP {status}). API key aur model naam check karein."}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Network error NVIDIA API tak pahunchte waqt: {e}"}
    except (KeyError, IndexError, ValueError) as e:
        return {"ok": False, "error": f"NVIDIA se anexpected response mila: {e}"}
