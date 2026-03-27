/**
 * Generic XBRL-style segment data parser.
 *
 * Handles multi-dimensional financial segment data where:
 *   item.name       = metric  (e.g. "us-gaap:RevenueFromContractWithCustomer…")
 *   segment.axis    = dimension  (e.g. "srt:ProductOrServiceAxis")
 *   segment.key     = stable XBRL member key  (e.g. "srt:Services")
 *   segment.label   = human-readable display name  (e.g. "Services")
 *
 * Nothing in this module is company- or label-specific.
 * All uniqueness guarantees are based on segment.key, NEVER segment.label.
 */

import type { SegmentedRevenuePeriod } from "@/lib/api";

// Tolerance for aggregate-sum detection (1%)
const AGG_TOLERANCE = 0.01;

/** Stable synthetic key for the "Other" collapsed bucket */
export const OTHER_KEY = "__other__";

// ── Output type ───────────────────────────────────────────────────────────────

export interface ParsedSegment {
  key:    string;   // segment.key  — stable XBRL identifier, use as React key
  label:  string;   // segment.label — display only, never use as key
  value:  number;   // item.amount
  axis:   string;   // segment.axis
  metric: string;   // item.name
  period: string;   // report_period of the source row
}

export interface ParseOptions {
  metric_name: string;          // required: filter items by item.name
  axis:        string;          // required: filter segments by segment.axis
  period?:     string;          // target report_period; default: latest
  dedupe?:     boolean;         // deduplicate by segment.key; default true
  leaf_only?:  boolean;         // exclude aggregates; default true
}

// ── Core parser ───────────────────────────────────────────────────────────────

/**
 * Extract clean, chart-ready segment data from raw segmented revenue periods.
 *
 * - Filters by metric_name (item.name) and axis (segment.axis)
 * - Excludes aggregate rows (items with 0 or >1 segments)
 * - Deduplicates by segment.key (NEVER by label)
 * - Removes "grand total" rows (value ≈ sum of all siblings)
 * - Returns the latest period unless `options.period` is specified
 */
export function parseSegments(
  periods: SegmentedRevenuePeriod[],
  options: ParseOptions,
): ParsedSegment[] {
  const { metric_name, axis, period, dedupe = true, leaf_only = true } = options;

  if (!periods.length) return [];

  // Sort DESC by report_period, pick target
  const sorted = [...periods].sort((a, b) =>
    b.report_period.localeCompare(a.report_period)
  );
  const target = period
    ? sorted.find(p => p.report_period === period)
    : sorted[0];
  if (!target) return [];

  const reportPeriod = target.report_period;
  const seenKeys     = new Set<string>();
  const results: ParsedSegment[] = [];

  for (const item of target.items) {
    // ── 1. Filter by metric ──────────────────────────────────────────────────
    if (item.name !== metric_name) continue;

    const segs = item.segments;

    // ── 2. Filter by axis + enforce leaf constraint ──────────────────────────
    if (leaf_only) {
      // Items with no segments are dimension-less totals → aggregate
      if (segs.length === 0) continue;
      // Items spanning multiple segment tags → cross-dimensional → aggregate
      if (segs.length !== 1) continue;
      if (segs[0].axis !== axis) continue;
    } else {
      const axisSegs = segs.filter(s => s.axis === axis);
      if (axisSegs.length !== 1) continue;
    }

    const seg = segs[0];
    if (!seg.key) continue;

    // ── 3. Deduplication by key (NEVER by label) ────────────────────────────
    if (dedupe && seenKeys.has(seg.key)) continue;
    seenKeys.add(seg.key);

    results.push({
      key:    seg.key,
      label:  seg.label || seg.key,
      value:  item.amount,
      axis,
      metric: metric_name,
      period: reportPeriod,
    });
  }

  // ── 4. Remove aggregate totals ───────────────────────────────────────────
  return leaf_only ? removeAggregates(results) : results;
}


function removeAggregates(segs: ParsedSegment[]): ParsedSegment[] {
  if (segs.length < 2) return segs;
  const total = segs.reduce((s, x) => s + x.value, 0);
  return segs.filter(seg => {
    const othersSum = total - seg.value;
    // If this value ≈ sum of all others, it's a grand-total row → drop it
    return !(othersSum > 0 && Math.abs(seg.value - othersSum) / othersSum < AGG_TOLERANCE);
  });
}


// ── Discovery helpers ─────────────────────────────────────────────────────────

/** Return all unique axis identifiers present in the latest period. */
export function discoverAxes(periods: SegmentedRevenuePeriod[]): string[] {
  if (!periods.length) return [];
  const latest = latestPeriod(periods);
  const axes   = new Set<string>();
  for (const item of latest.items) {
    for (const seg of item.segments) {
      if (seg.axis) axes.add(seg.axis);
    }
  }
  return [...axes];
}

/**
 * Return the metric name (item.name) with the most leaf items for *axis*
 * in the latest period.  Used to auto-select the primary metric.
 */
export function dominantMetric(
  periods: SegmentedRevenuePeriod[],
  axis:    string,
): string | null {
  if (!periods.length) return null;
  const latest = latestPeriod(periods);
  const counts = new Map<string, number>();
  for (const item of latest.items) {
    if (item.segments.length === 1 && item.segments[0].axis === axis) {
      counts.set(item.name, (counts.get(item.name) ?? 0) + 1);
    }
  }
  if (!counts.size) return null;
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
}

function latestPeriod(periods: SegmentedRevenuePeriod[]): SegmentedRevenuePeriod {
  return [...periods].sort((a, b) =>
    b.report_period.localeCompare(a.report_period)
  )[0];
}


// ── Axis label map (generic fallback for unknown axes) ────────────────────────

export interface AxisLabels {
  title:     string;   // section heading
  donut:     string;   // donut chart sub-title
  hist:      string;   // historical bar chart sub-title
}

const AXIS_LABEL_MAP: Record<string, AxisLabels> = {
  "srt:ProductOrServiceAxis": {
    title: "Product & Service Breakdown",
    donut: "Revenue by Product",
    hist:  "Historical Revenue by Product",
  },
  "srt:StatementGeographicalAxis": {
    title: "Geographic Breakdown",
    donut: "Revenue by Geography",
    hist:  "Historical Revenue by Geography",
  },
  "us-gaap:StatementBusinessSegmentsAxis": {
    title: "Business Segment Breakdown",
    donut: "Revenue by Segment",
    hist:  "Historical Revenue by Segment",
  },
};

/**
 * Return human-readable labels for a given axis URI.
 * Falls back gracefully for unknown axes using the local part of the CURIE.
 */
export function axisLabels(axis: string): AxisLabels {
  if (axis in AXIS_LABEL_MAP) return AXIS_LABEL_MAP[axis];
  // Derive a reasonable label from the XBRL CURIE  e.g. "foo:BarBazAxis" → "Bar Baz"
  const local     = axis.split(":").pop() ?? axis;
  const humanized = local.replace(/Axis$/, "").replace(/([A-Z])/g, " $1").trim();
  return {
    title: `${humanized} Breakdown`,
    donut: `Revenue by ${humanized}`,
    hist:  `Historical Revenue by ${humanized}`,
  };
}
