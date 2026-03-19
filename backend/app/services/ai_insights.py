"""AI-powered investment insights — supports Anthropic (Claude) and OpenAI.

Cache strategy
--------------
  Key : alphadesk:ai_insight:{TICKER}:{provider}
  TTL : 7 days (604 800 s)

Provider selection is automatic:
  1. Use the first provider with a configured API key
     (preference order: anthropic → openai)
  2. If no keys are configured, generate_ai_insights returns an
     "unavailable" response — never raises.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal

import anthropic
import openai as _openai

from app.config import get_settings

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
Provider = Literal["anthropic", "openai"]

AI_INSIGHT_TTL    = 7 * 24 * 3600
_CACHE_PREFIX     = "alphadesk:ai_insight"
_ANTHROPIC_MODEL  = "claude-haiku-4-5-20251001"
_OPENAI_MODEL     = "gpt-4.1-mini"

PROVIDER_MODELS: dict[str, str] = {
    "anthropic": _ANTHROPIC_MODEL,
    "openai":    _OPENAI_MODEL,
}

_PROVIDER_PRIORITY: list[Provider] = ["anthropic", "openai"]


def _get_available_provider() -> tuple[Provider, str] | None:
    """Return (provider, api_key) for the first configured provider, or None."""
    s = get_settings()
    keys: dict[Provider, str] = {
        "anthropic": s.ANTHROPIC_API_KEY,
        "openai":    s.OPENAI_API_KEY,
    }
    for p in _PROVIDER_PRIORITY:
        if keys[p]:
            return p, keys[p]
    return None


# ── Cache key ─────────────────────────────────────────────────────────────────

def ai_cache_key(ticker: str, provider: Provider = "anthropic") -> str:
    return f"{_CACHE_PREFIX}:{ticker.upper()}:{provider}"


# ── Context builder ───────────────────────────────────────────────────────────

def _pct(v: float | None, d: int = 1) -> str:
    if v is None: return "N/A"
    return f"{v * 100:.{d}f}%"

def _mul(v: float | None, d: int = 1) -> str:
    if v is None or v <= 0: return "N/A"
    return f"{v:.{d}f}×"

def _bil(v: float | None) -> str:
    if v is None: return "N/A"
    a = abs(v)
    if a >= 1e12: return f"${v / 1e12:.2f}T"
    if a >= 1e9:  return f"${v / 1e9:.1f}B"
    if a >= 1e6:  return f"${v / 1e6:.1f}M"
    return f"${v:,.0f}"


def build_financial_context(ticker: str, data: dict) -> str:
    """Produce a compact, structured text block for the AI prompt."""
    m       = (data.get("metrics") or {}).get("snapshot") or {}
    p       = (data.get("overview") or {}).get("profile")  or {}
    company = (data.get("overview") or {}).get("company")  or {}
    fin     = data.get("financials") or {}
    ttm     = fin.get("income_ttm")   or {}
    bttm    = fin.get("balance_ttm")  or {}
    cttm    = fin.get("cashflow_ttm") or {}
    income  = fin.get("income_annual") or []
    estimates = (data.get("estimates") or {}).get("annual") or []

    # 3-year revenue CAGR
    rev_cagr = "N/A"
    valid_rev = [r["revenue"] for r in income[:5] if r.get("revenue") and r["revenue"] > 0]
    if len(valid_rev) >= 4:
        cagr_val = ((valid_rev[0] / valid_rev[3]) ** (1 / 3) - 1) * 100
        rev_cagr = f"{cagr_val:.1f}%"

    # Analyst forward estimates
    next_yr_rev_g = "N/A"
    next_yr_eps_g = "N/A"
    if estimates:
        est     = estimates[0]
        ttm_rev = ttm.get("revenue")
        ttm_eps = ttm.get("earnings_per_share")
        if est.get("revenue") and ttm_rev and ttm_rev > 0:
            g = ((est["revenue"] - ttm_rev) / ttm_rev) * 100
            next_yr_rev_g = f"{g:+.1f}%"
        if est.get("earnings_per_share") and ttm_eps and ttm_eps != 0:
            g = ((est["earnings_per_share"] - ttm_eps) / abs(ttm_eps)) * 100
            next_yr_eps_g = f"{g:+.1f}%"

    lines = [
        f"Company : {company.get('name', ticker)} ({ticker})",
        f"Sector  : {company.get('sector',   'N/A')}",
        f"Industry: {company.get('industry', 'N/A')}",
        "",
        "=== GROWTH ===",
        f"Revenue Growth (YoY)    : {_pct(m.get('revenue_growth') or p.get('revenue_growth'))}",
        f"Revenue CAGR (3Y)       : {rev_cagr}",
        f"Est. Revenue Growth +1Y : {next_yr_rev_g}",
        f"Est. EPS Growth +1Y     : {next_yr_eps_g}",
        "",
        "=== PROFITABILITY ===",
        f"Gross Margin     : {_pct(m.get('gross_margin')     or p.get('gross_margins'))}",
        f"Operating Margin : {_pct(m.get('operating_margin') or p.get('operating_margins'))}",
        f"Net Margin       : {_pct(m.get('net_margin')       or p.get('profit_margins'))}",
        f"ROIC             : {_pct(m.get('return_on_invested_capital'))}",
        f"ROE              : {_pct(m.get('return_on_equity') or p.get('roe'))}",
        f"Free Cash Flow   : {_bil(cttm.get('free_cash_flow'))}",
        f"FCF Yield        : {_pct(m.get('free_cash_flow_yield'))}",
        "",
        "=== BALANCE SHEET ===",
        f"Cash & Equivalents : {_bil(bttm.get('cash_and_equivalents'))}",
        f"Total Debt         : {_bil(bttm.get('total_debt'))}",
        f"Debt / Equity      : {m.get('debt_to_equity') or p.get('debt_to_equity') or 'N/A'}",
        f"Current Ratio      : {m.get('current_ratio')  or p.get('current_ratio')  or 'N/A'}",
        "",
        "=== VALUATION ===",
        f"P/E (Trailing) : {_mul(m.get('price_to_earnings_ratio') or p.get('pe_ratio'))}",
        f"P/E (Forward)  : {_mul(p.get('forward_pe'))}",
        f"PEG Ratio      : {_mul(m.get('peg_ratio') or p.get('peg_ratio'), 2)}",
        f"EV / EBITDA    : {_mul(m.get('enterprise_value_to_ebitda_ratio'))}",
        f"EV / Revenue   : {_mul(p.get('ev_revenue'))}",
        f"Market Cap     : {_bil(p.get('market_cap'))}",
        "",
        "=== MARKET INDICATORS ===",
        f"Short Interest (% float) : {_pct(p.get('short_pct_float'))}",
        f"Institutional Ownership  : {_pct(p.get('held_pct_institutions'))}",
        f"Beta                     : {p.get('beta') or 'N/A'}",
    ]
    return "\n".join(lines)


# ── Shared prompt ─────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are a professional equity research analyst at a top-tier investment bank. "
    "Generate concise, structured investment insights from structured financial data. "
    "Be factually accurate and specific. Do not speculate beyond what the data supports. "
    "Cite actual data points rather than making generic statements."
)

def _user_prompt(context: str) -> str:
    return f"""Analyze the following company financial profile and return a JSON object.

{context}

Return ONLY a valid JSON object — no markdown fences, no extra text — with exactly these fields:
{{
  "summary": "Executive summary of business quality and investment case. Max 80 words.",
  "strengths": ["Up to 4 specific data-driven strengths, each max 25 words."],
  "weaknesses": ["Up to 4 specific data-driven weaknesses or concerns, each max 25 words."],
  "drivers": ["Up to 4 key long-term growth drivers or catalysts, each max 25 words."],
  "risks": ["Up to 4 key investment risks, each max 25 words."],
  "valuation_view": "One sentence on valuation attractiveness, citing specific multiples. Max 40 words."
}}"""


# ── Provider-specific callers ─────────────────────────────────────────────────

async def _call_anthropic(context: str, api_key: str) -> str:
    client   = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=_ANTHROPIC_MODEL,
        max_tokens=1024,
        temperature=0.2,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _user_prompt(context)}],
    )
    return response.content[0].text.strip()


async def _call_openai(context: str, api_key: str) -> str:
    client   = _openai.AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=_OPENAI_MODEL,
        max_tokens=1024,
        temperature=0.2,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": _user_prompt(context)},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def _strip_fences(raw: str) -> str:
    """Remove accidental ```json ... ``` wrapping."""
    if raw.startswith("```"):
        lines = raw.split("\n")
        end   = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        raw   = "\n".join(lines[1:end])
    return raw


# ── Public entry point ────────────────────────────────────────────────────────

def _unavailable_response() -> dict:
    """Deterministic response when no AI provider is configured."""
    return {
        "summary": "",
        "strengths": [],
        "weaknesses": [],
        "drivers": [],
        "risks": [],
        "valuation_view": "",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": None,
        "provider": None,
        "available": False,
        "_source": "none",
    }


async def generate_ai_insights(
    ticker: str,
    data:   dict,
    cache:  Any,
) -> dict:
    """
    Return AI investment insights for *ticker*.

    Provider is chosen automatically based on configured API keys
    (preference: anthropic → openai). If no keys are set, returns
    an "unavailable" response with available=False.

    Returned dict keys:
      summary, strengths, weaknesses, drivers, risks, valuation_view,
      generated_at, model, provider, available, _source
    """
    resolved = _get_available_provider()
    if resolved is None:
        log.warning("AI insights unavailable for %s: no API keys configured", ticker)
        return _unavailable_response()

    provider, api_key = resolved
    model_id = PROVIDER_MODELS[provider]
    key      = ai_cache_key(ticker, provider)

    # ── Cache hit ─────────────────────────────────────────────────────────────
    cached = await cache.get(key)
    if cached:
        result = json.loads(cached)
        result["_source"]   = "cache"
        result["available"] = True
        return result

    # ── Generate ──────────────────────────────────────────────────────────────
    context = build_financial_context(ticker, data)
    callers = {"anthropic": _call_anthropic, "openai": _call_openai}
    raw     = await callers[provider](context, api_key)
    raw     = _strip_fences(raw)

    result: dict = json.loads(raw)

    for field in ("summary", "valuation_view"):
        result.setdefault(field, "")
    for field in ("strengths", "weaknesses", "drivers", "risks"):
        result.setdefault(field, [])
        result[field] = list(result[field])[:4]

    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["model"]        = model_id
    result["provider"]     = provider
    result["available"]    = True
    result["_source"]      = "generated"

    await cache.set(key, json.dumps(result), AI_INSIGHT_TTL)
    return result
