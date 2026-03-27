"""
Overview synthesis — Tavily retrieval + OpenAI structured narrative.

Implements the AI-powered analysis layer for the Research Overview tab.
All AI outputs are labeled source_type='Estimated'.

Fallback hierarchy:
  1. Cache hit → return immediately
  2. Tavily + OpenAI → full narrative
  3. Only Tavily  → skip narrative, mark unavailable
  4. Only OpenAI  → skip Tavily context, generate from backend facts
  5. Neither      → return { available: False }
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.database import Cache

log      = logging.getLogger(__name__)
settings = get_settings()

_TAVILY_TTL   = 21_600   # 6 hours
_SYNTHESIS_TTL = 21_600  # 6 hours
_PROMPT_VERSION = "v1"
_MODEL           = "gpt-4.1-mini"


# ── Cache keys ────────────────────────────────────────────────────────────────

def _hour_bucket() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.month:02d}-{now.day:02d}-{now.hour // 6 * 6:02d}"


def _tavily_key(ticker: str) -> str:
    return f"research:tavily:{ticker.upper()}:{_hour_bucket()}"


def _synthesis_key(ticker: str) -> str:
    return f"research:synthesis:{ticker.upper()}:{_hour_bucket()}"


# ── Tavily retrieval ──────────────────────────────────────────────────────────

async def _fetch_tavily(ticker: str, company_name: str, sector: str) -> dict:
    try:
        from tavily import TavilyClient  # type: ignore
        client = TavilyClient(api_key=settings.TAVILY_API_KEY)

        queries = [
            f"{company_name} {ticker} news earnings guidance 2025 2026",
            f"{sector} industry trends {company_name} outlook",
        ]

        results: list[dict] = []
        for query in queries:
            resp = client.search(
                query=query,
                search_depth="basic",
                max_results=5,
                include_answer=False,
            )
            for r in (resp.get("results") or []):
                results.append({
                    "title":          r.get("title", ""),
                    "url":            r.get("url", ""),
                    "snippet":        (r.get("content") or "")[:400],
                    "published_date": r.get("published_date", ""),
                })

        return {
            "available":    True,
            "results":      results[:8],
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        log.warning("overview_synthesis: Tavily failed for %s: %s", ticker, exc)
        return {"available": False, "results": [], "retrieved_at": None}


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(
    ticker: str,
    company_name: str,
    research_data: dict,
    analysis_layer: dict,
    tavily: dict,
) -> str:
    snap      = (research_data.get("overview") or {}).get("snapshot") or {}
    m         = (research_data.get("metrics") or {}).get("snapshot") or {}
    profile   = (research_data.get("overview") or {}).get("profile") or {}
    anomalies = (research_data.get("analysis") or {}).get("anomalies") or []
    news      = research_data.get("news") or []
    pillars   = analysis_layer.get("pillars") or []
    sentiment = analysis_layer.get("sentiment_regime") or {}

    price   = snap.get("price", "N/A")
    mktcap  = profile.get("market_cap")
    mktcap_str = f"${mktcap/1e9:.1f}B" if mktcap else "N/A"
    rev_g   = m.get("revenue_growth")
    rev_g_str = f"{rev_g*100:.1f}%" if rev_g is not None else "N/A"
    op_m    = m.get("operating_margin")
    op_m_str  = f"{op_m*100:.1f}%" if op_m is not None else "N/A"

    pillar_lines = "\n".join(
        f"  - {p['key'].replace('_', ' ').title()}: {p['label']} "
        f"({p.get('primary_metric','')}: {p.get('primary_value','')})"
        for p in pillars
        if p.get("label") != "N/A"
    ) or "  Not available"

    anom_lines = "\n".join(
        f"  [{a['severity'].upper()}] {a['title']}: {a['description']}"
        for a in anomalies[:5]
    ) or "  None detected"

    news_lines = "\n".join(
        f"  - {n.get('title','')[:120]} ({n.get('source','')})"
        for n in news[:5]
    ) or "  No recent news"

    tavily_block = ""
    if tavily.get("available") and tavily.get("results"):
        tavily_block = "FRESH MARKET CONTEXT (Tavily web retrieval):\n"
        for r in tavily["results"][:6]:
            tavily_block += (
                f"  [{r.get('published_date','recent')}] {r['title']}\n"
                f"  {r['snippet'][:200]}\n\n"
            )

    return f"""You are a disciplined institutional equity research analyst writing a concise brief on {company_name} ({ticker}).

BACKEND FACTS — do NOT recalculate, override, or contradict these values:
- Price: ${price}
- Market Cap: {mktcap_str}
- Revenue Growth: {rev_g_str}
- Operating Margin: {op_m_str}
- Sentiment Regime: {sentiment.get('score','N/A')} / 100 — "{sentiment.get('label','N/A')}" (do not recalculate)

PILLAR ASSESSMENTS (computed deterministically — do not override):
{pillar_lines}

FINANCIAL ANOMALIES (computed):
{anom_lines}

RECENT NEWS (AlphaTrack data):
{news_lines}

{tavily_block}RULES — violations make the output unusable:
1. Use ONLY the data in this prompt. Invent nothing.
2. Do NOT recalculate the sentiment score.
3. Say so explicitly when evidence is insufficient — never fabricate.
4. Prefer uncertainty over overconfidence.
5. No retail-style phrases: "strong buy", "sniper entry", "moonshot", "guaranteed upside".
6. Tone: concise equity research note. Max 25 words per bullet. Max 3 bullets per array.
7. For news_enrichment: pick 1–3 news items that matter most; explain WHY in one sentence each.

Return ONLY valid JSON:
{{
  "stance": "bullish" | "neutral" | "bearish" | "insufficient_data",
  "summary_bullets": ["<string>"],
  "what_changed": ["<string>"],
  "why_now": ["<string>"],
  "thesis_breakers": ["<string>"],
  "news_enrichment": [{{"headline": "<string>", "why_it_matters": "<string>", "tag": "<string>"}}],
  "confidence_note": "<string>"
}}"""


# ── OpenAI call ───────────────────────────────────────────────────────────────

async def _call_openai(prompt: str, ticker: str) -> dict | None:
    try:
        from openai import AsyncOpenAI  # type: ignore
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        resp = await client.chat.completions.create(
            model=_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a disciplined institutional equity research analyst. "
                        "You produce evidence-backed, concise analysis. "
                        "You never invent data or compute metrics. "
                        "You never use retail-style language. "
                        "Return valid JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=900,
            temperature=0.3,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as exc:
        log.warning("overview_synthesis: OpenAI failed for %s: %s", ticker, exc)
        return None


# ── Public interface ──────────────────────────────────────────────────────────

async def get_overview_synthesis(
    ticker: str,
    force: bool,
    cache: Cache,
    research_data: dict,
    analysis_layer: dict,
) -> dict:
    """
    Return AI-powered overview synthesis for ticker.
    Cached per 6-hour bucket. Falls back gracefully if providers unavailable.
    """
    synth_key = _synthesis_key(ticker)

    # Cache hit
    if not force:
        cached = await cache.get(synth_key)
        if cached:
            try:
                result = json.loads(cached)
                result["_source"] = "cache"
                return result
            except Exception:
                pass

    has_openai = bool(settings.OPENAI_API_KEY)
    has_tavily = bool(getattr(settings, "TAVILY_API_KEY", ""))

    company     = (research_data.get("overview") or {}).get("company") or {}
    company_name = company.get("name", ticker)
    sector       = company.get("sector", "")

    # Tavily retrieval (from cache or fresh)
    tavily_result = {"available": False, "results": [], "retrieved_at": None}
    if has_tavily:
        tv_key = _tavily_key(ticker)
        if not force:
            tv_cached = await cache.get(tv_key)
            if tv_cached:
                try:
                    tavily_result = json.loads(tv_cached)
                except Exception:
                    pass

        if not tavily_result.get("available"):
            tavily_result = await _fetch_tavily(ticker, company_name, sector)
            if tavily_result.get("available"):
                await cache.set(tv_key, json.dumps(tavily_result), _TAVILY_TTL)

    # OpenAI synthesis
    narrative: dict | None = None
    if has_openai:
        prompt    = _build_prompt(ticker, company_name, research_data, analysis_layer, tavily_result)
        narrative = await _call_openai(prompt, ticker)

    now = datetime.now(timezone.utc).isoformat()

    if narrative:
        result: dict = {
            "available":             True,
            "stance":                narrative.get("stance", "insufficient_data"),
            "summary_bullets":       narrative.get("summary_bullets", []),
            "what_changed":          narrative.get("what_changed", []),
            "why_now":               narrative.get("why_now", []),
            "thesis_breakers":       narrative.get("thesis_breakers", []),
            "news_enrichment":       narrative.get("news_enrichment", []),
            "confidence_note":       narrative.get("confidence_note", ""),
            "type":                  "Estimated",
            "generated_at":          now,
            "model":                 _MODEL,
            "provider":              "openai",
            "prompt_version":        _PROMPT_VERSION,
            "tavily_retrieved_at":   tavily_result.get("retrieved_at"),
            "fresh_context_available": tavily_result.get("available", False),
            "_source":               "generated",
        }
    else:
        result = {
            "available":             False,
            "stance":                None,
            "summary_bullets":       [],
            "what_changed":          [],
            "why_now":               [],
            "thesis_breakers":       [],
            "news_enrichment":       [],
            "confidence_note":       "",
            "type":                  "Estimated",
            "generated_at":          now,
            "model":                 None,
            "provider":              None,
            "prompt_version":        _PROMPT_VERSION,
            "tavily_retrieved_at":   tavily_result.get("retrieved_at"),
            "fresh_context_available": tavily_result.get("available", False),
            "_source":               "none",
        }

    await cache.set(synth_key, json.dumps(result, default=str), _SYNTHESIS_TTL)
    return result
