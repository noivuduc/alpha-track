"""
Generic XBRL-style segment data parser, validator, and normalizer.

Handles multi-dimensional financial segment data where:
  - item.name       = metric  (e.g. "us-gaap:RevenueFromContractWithCustomer…")
  - segment.axis    = dimension  (e.g. "srt:ProductOrServiceAxis")
  - segment.key     = stable XBRL member key  (e.g. "srt:Services")
  - segment.label   = human-readable display name  (e.g. "Services")

Nothing in this module is company- or label-specific.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Tolerance for aggregate-sum detection (1 %)
_AGG_TOLERANCE = 0.01


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass
class ParsedSegment:
    key:    str
    label:  str
    value:  float
    axis:   str
    metric: str
    period: str


# ── Core parser ───────────────────────────────────────────────────────────────

def parse_segments(
    periods:     list[dict],
    metric_name: str,
    axis:        str,
    period:      str | None = None,   # report_period string; default: latest
    dedupe:      bool       = True,
    leaf_only:   bool       = True,
) -> list[ParsedSegment]:
    """
    Extract clean, chart-ready segment data from raw segmented revenue periods.

    Parameters
    ----------
    periods     : raw list of SegmentedRevenuePeriod dicts from the FD API
    metric_name : XBRL item name to filter by (item["name"])
    axis        : XBRL axis to filter by (segment["axis"])
    period      : specific report_period to target; defaults to the latest
    dedupe      : skip duplicate segment.key entries within the same period
    leaf_only   : exclude aggregate rows (items with 0 or >1 segments,
                  and items whose value ≈ sum of all sibling values)

    Returns
    -------
    List of ParsedSegment — one entry per leaf node in the chosen period.
    """
    if not periods:
        return []

    # Sort DESC by report_period, pick target
    sorted_periods = sorted(
        periods,
        key=lambda p: p.get("report_period", ""),
        reverse=True,
    )
    if period:
        target = next(
            (p for p in sorted_periods if p.get("report_period") == period), None
        )
        if target is None:
            log.warning("parse_segments: period %r not found", period)
            return []
    else:
        target = sorted_periods[0]

    report_period = target.get("report_period", "")
    seen_keys: set[str] = set()
    results: list[ParsedSegment] = []

    for item in target.get("items", []):
        # ── 1. Filter by metric ────────────────────────────────────────────────
        if item.get("name") != metric_name:
            continue

        segs = item.get("segments", [])

        # ── 2. Filter by axis + enforce leaf constraint ────────────────────────
        if leaf_only:
            # Items with no segments are dimension-less totals → aggregate
            if len(segs) == 0:
                continue
            # Items spanning multiple segments (cross-dimensional) → aggregate
            if len(segs) != 1:
                continue
            if segs[0].get("axis") != axis:
                continue
        else:
            # Without leaf_only: still require exactly one segment on this axis
            axis_segs = [s for s in segs if s.get("axis") == axis]
            if len(axis_segs) != 1:
                continue

        seg     = segs[0]
        seg_key = seg.get("key", "")
        if not seg_key:
            log.debug(
                "parse_segments: missing key for metric=%s axis=%s label=%s",
                metric_name, axis, seg.get("label", "?"),
            )
            continue

        # ── 3. Deduplication by key (NEVER by label) ──────────────────────────
        if dedupe and seg_key in seen_keys:
            log.debug("parse_segments: dedupe skip key=%s", seg_key)
            continue
        seen_keys.add(seg_key)

        results.append(ParsedSegment(
            key    = seg_key,
            label  = seg.get("label") or seg_key,
            value  = float(item.get("amount", 0)),
            axis   = axis,
            metric = metric_name,
            period = report_period,
        ))

    # ── 4. Remove aggregate totals ─────────────────────────────────────────────
    if leaf_only:
        results = _remove_sum_aggregates(results)

    return results


def _remove_sum_aggregates(segs: list[ParsedSegment]) -> list[ParsedSegment]:
    """
    Remove any segment whose value ≈ sum of all other segments.
    These are total rows that slipped through the leaf_only filter because
    they still carry a single segment tag (e.g. the "all products" member).
    """
    if len(segs) < 2:
        return segs

    total = sum(s.value for s in segs)
    cleaned: list[ParsedSegment] = []
    for seg in segs:
        others_sum = total - seg.value
        if others_sum > 0 and abs(seg.value - others_sum) / others_sum < _AGG_TOLERANCE:
            log.debug(
                "parse_segments: removing aggregate key=%s value=%.0f ≈ sum_of_others=%.0f",
                seg.key, seg.value, others_sum,
            )
            continue
        cleaned.append(seg)
    return cleaned


# ── Discovery helpers ─────────────────────────────────────────────────────────

def discover_axes(periods: list[dict]) -> list[str]:
    """Return all unique axis identifiers present in the latest period."""
    if not periods:
        return []
    latest = _latest_period(periods)
    axes: set[str] = set()
    for item in latest.get("items", []):
        for seg in item.get("segments", []):
            ax = seg.get("axis", "")
            if ax:
                axes.add(ax)
    return sorted(axes)


def discover_metrics(periods: list[dict]) -> list[str]:
    """Return all unique metric names present in the latest period."""
    if not periods:
        return []
    latest = _latest_period(periods)
    metrics: set[str] = set()
    for item in latest.get("items", []):
        name = item.get("name", "")
        if name:
            metrics.add(name)
    return sorted(metrics)


def dominant_metric(periods: list[dict], axis: str) -> str | None:
    """
    Return the metric name that has the most leaf items for *axis*.
    Used to auto-select the primary metric when the caller doesn't specify one.
    """
    if not periods:
        return None
    latest = _latest_period(periods)
    counts: dict[str, int] = {}
    for item in latest.get("items", []):
        segs = item.get("segments", [])
        if len(segs) == 1 and segs[0].get("axis") == axis:
            name = item.get("name", "")
            if name:
                counts[name] = counts.get(name, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def _latest_period(periods: list[dict]) -> dict:
    return max(periods, key=lambda p: p.get("report_period", ""))


# ── Validation ────────────────────────────────────────────────────────────────

def validate_segments(periods: list[dict], ticker: str = "") -> None:
    """
    Log warnings for data anomalies.  Called before caching so issues
    surface early and don't silently corrupt the frontend.

    Checks:
      • duplicate segment.key within the same (metric, axis) context
      • items spanning multiple axes (informational — not an error)
      • missing segment keys
    """
    if not periods:
        return

    for period_data in periods:
        rp    = period_data.get("report_period", "?")
        items = period_data.get("items", [])

        # (metric, axis, key) → occurrence count
        seen: dict[tuple[str, str, str], int] = {}
        missing_key_count = 0

        for item in items:
            metric = item.get("name", "")
            for seg in item.get("segments", []):
                key = seg.get("key", "")
                if not key:
                    missing_key_count += 1
                    continue
                ctx = (metric, seg.get("axis", ""), key)
                seen[ctx] = seen.get(ctx, 0) + 1

        for (metric, ax, key), count in seen.items():
            if count > 1:
                log.warning(
                    "segments [%s %s]: duplicate (metric=%s, axis=%s, key=%s) ×%d",
                    ticker, rp, metric, ax, key, count,
                )

        if missing_key_count:
            log.warning(
                "segments [%s %s]: %d segment(s) have no key",
                ticker, rp, missing_key_count,
            )

        multi_axis = [
            item for item in items
            if len({s.get("axis", "") for s in item.get("segments", [])}) > 1
        ]
        if multi_axis:
            log.debug(
                "segments [%s %s]: %d cross-dimensional items",
                ticker, rp, len(multi_axis),
            )
