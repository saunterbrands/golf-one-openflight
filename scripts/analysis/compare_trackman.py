"""Pair OpenFlight shots with Trackman shots and emit a side-by-side
comparison CSV.

Usage::

    uv run python scripts/analysis/compare_trackman.py \\
        --openflight session_logs/session_20260506_*.jsonl \\
        --trackman ~/Downloads/TrackMan_2026-05-06.csv \\
        --output ~/openflight_sessions/comparison_20260506.csv

Pairing strategy
----------------
Both systems number shots sequentially but their numbering doesn't
necessarily align (one of them may miss a shot, or you may have
hit a couple of "warm up" shots only one was watching). To be
robust:

1. Group both systems' shots by club.
2. Within each club, pair shots in chronological order.
3. Reject pairs whose ball-speed delta exceeds ``--ball-speed-tol``
   mph — flags missing/extra shots so you can fix the alignment by
   hand.

The output CSV has both systems' values + deltas + a
``match_quality`` column (``good``, ``ball_speed_mismatch``,
``unmatched_openflight``, ``unmatched_trackman``).

Trackman CSV column handling
----------------------------
Different Trackman exports (TPS, Range, TM4) use slightly different
column headers. We map known aliases to canonical names; anything
unknown is preserved verbatim in the output.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Trackman CSV column aliases
# ---------------------------------------------------------------------------

# Each canonical field maps to a list of header substrings (case-folded,
# whitespace-stripped). The first header that *contains* any alias as a
# substring wins — Trackman exports add unit suffixes like "(mph)" that
# we don't want to anchor on.
_TM_ALIASES: Dict[str, List[str]] = {
    "ball_speed_mph":          ["ball speed", "ballspeed"],
    "club_speed_mph":          ["club speed", "clubspeed", "club head speed", "clubheadspeed"],
    "smash_factor":            ["smash factor", "smashfactor"],
    "launch_angle_vertical":   ["launch angle v", "launch angle (v)", "vertical launch", "launch angle"],
    "launch_angle_horizontal": ["launch direction", "launch angle h", "side angle", "azimuth"],
    "spin_rpm":                ["spin rate", "total spin", "spinrate"],
    "carry_yards":             ["carry distance", "carry"],
    "club":                    ["club type", "club name", "club"],
    "shot_number":             ["shot number", "shotnumber", "shot"],
    "timestamp":               ["date/time", "datetime", "timestamp", "time", "date"],
}


def _canon_header(h: str) -> str:
    return h.strip().lower().replace("_", " ")


def _detect_units(headers: List[str]) -> Dict[str, str]:
    """Return a unit hint per canonical field by inspecting the header
    suffix. Currently only used for ball/club speed (mph vs km/h vs m/s)
    and carry (yards vs metres).
    """
    units: Dict[str, str] = {}
    for h in headers:
        ch = _canon_header(h)
        if "ball speed" in ch or "club speed" in ch or "club head speed" in ch:
            if "kph" in ch or "km/h" in ch or "kmh" in ch:
                units.setdefault("speed", "kph")
            elif "m/s" in ch:
                units.setdefault("speed", "mps")
            else:
                units.setdefault("speed", "mph")
        if "carry" in ch:
            if "metre" in ch or "meter" in ch or "(m)" in ch or " m " in ch:
                units.setdefault("carry", "m")
            else:
                units.setdefault("carry", "yards")
    return units


def _build_column_map(headers: List[str]) -> Dict[str, str]:
    """Map canonical-field-name → actual-header-string from the CSV."""
    col_map: Dict[str, str] = {}
    canon = {_canon_header(h): h for h in headers}
    # Iterate aliases in declared order so longer / more specific
    # aliases are matched first within a single field.
    for field_name, aliases in _TM_ALIASES.items():
        for alias in aliases:
            for canon_h, raw_h in canon.items():
                if alias in canon_h and field_name not in col_map:
                    col_map[field_name] = raw_h
                    break
            if field_name in col_map:
                break
    return col_map


# ---------------------------------------------------------------------------
# Club name normalization
# ---------------------------------------------------------------------------

# A loose normalizer: strip case/whitespace/dashes, accept "7i" / "7iron"
# / "7-iron" / "iron 7" etc. Both systems should agree after normalization.
_CLUB_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(driver|drv|1w|1-wood)\b"),     "driver"),
    (re.compile(r"\b(\d)\s*-?\s*(wood|w)\b"),        r"\1-wood"),
    (re.compile(r"\b(\d)\s*-?\s*(hybrid|h|hy)\b"),   r"\1-hybrid"),
    (re.compile(r"\b(\d)\s*-?\s*(iron|i)\b"),        r"\1-iron"),
    (re.compile(r"\biron\s*-?\s*(\d)\b"),            r"\1-iron"),
    (re.compile(r"\bpitching\s*wedge\b|\bpw\b"),     "pw"),
    (re.compile(r"\bgap\s*wedge\b|\bgw\b"),          "gw"),
    (re.compile(r"\bsand\s*wedge\b|\bsw\b"),         "sw"),
    (re.compile(r"\blob\s*wedge\b|\blw\b"),          "lw"),
]


def normalize_club(raw: Optional[str]) -> str:
    if raw is None:
        return ""
    s = str(raw).strip().lower()
    if not s:
        return ""
    for pat, repl in _CLUB_PATTERNS:
        m = pat.search(s)
        if m:
            return pat.sub(repl, m.group(0)).strip()
    return s


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

@dataclass
class Shot:
    """Canonical per-shot record used by both sources."""
    source: str  # "of" or "tm"
    shot_number: Optional[int]
    timestamp: Optional[datetime]
    club: str
    ball_speed_mph: Optional[float] = None
    club_speed_mph: Optional[float] = None
    smash_factor: Optional[float] = None
    launch_angle_vertical: Optional[float] = None
    launch_angle_horizontal: Optional[float] = None
    spin_rpm: Optional[float] = None
    carry_yards: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> Optional[int]:
    f = _to_float(v)
    return int(f) if f is not None else None


def _parse_timestamp(v: Any) -> Optional[datetime]:
    if v is None or v == "":
        return None
    s = str(v).strip()
    # Try ISO first (OpenFlight), then a few common Trackman formats.
    candidates = [
        None,  # let fromisoformat try
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ]
    for fmt in candidates:
        try:
            if fmt is None:
                return datetime.fromisoformat(s)
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def load_openflight(path: Path) -> List[Shot]:
    """Load `shot_detected` entries from an OpenFlight JSONL session log."""
    shots: List[Shot] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "shot_detected":
                continue
            data = entry.get("data", entry)  # tolerate flat or nested
            shots.append(Shot(
                source="of",
                shot_number=_to_int(data.get("shot_number")),
                timestamp=_parse_timestamp(entry.get("timestamp")
                                           or data.get("timestamp")),
                club=normalize_club(data.get("club")),
                ball_speed_mph=_to_float(data.get("ball_speed_mph")),
                club_speed_mph=_to_float(data.get("club_speed_mph")),
                smash_factor=_to_float(data.get("smash_factor")),
                launch_angle_vertical=_to_float(
                    data.get("launch_angle_vertical")),
                launch_angle_horizontal=_to_float(
                    data.get("launch_angle_horizontal")),
                spin_rpm=_to_float(data.get("spin_rpm")),
                carry_yards=_to_float(
                    data.get("carry_spin_adjusted")
                    or data.get("estimated_carry_yards")),
                raw=data,
            ))
    return shots


def load_trackman(path: Path) -> List[Shot]:
    """Load shots from a Trackman CSV export. Tolerant of header
    variations (TPS / Range / TM4)."""
    shots: List[Shot] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return shots
        col_map = _build_column_map(list(reader.fieldnames))
        units = _detect_units(list(reader.fieldnames))
        speed_unit = units.get("speed", "mph")
        carry_unit = units.get("carry", "yards")

        def _get(row: Dict[str, str], canon: str) -> Any:
            col = col_map.get(canon)
            return row.get(col) if col else None

        for row in reader:
            ball = _to_float(_get(row, "ball_speed_mph"))
            club_sp = _to_float(_get(row, "club_speed_mph"))
            if speed_unit == "kph":
                if ball is not None: ball /= 1.609344
                if club_sp is not None: club_sp /= 1.609344
            elif speed_unit == "mps":
                if ball is not None: ball *= 2.236936
                if club_sp is not None: club_sp *= 2.236936
            carry = _to_float(_get(row, "carry_yards"))
            if carry_unit == "m" and carry is not None:
                carry *= 1.093613

            shots.append(Shot(
                source="tm",
                shot_number=_to_int(_get(row, "shot_number")),
                timestamp=_parse_timestamp(_get(row, "timestamp")),
                club=normalize_club(_get(row, "club")),
                ball_speed_mph=ball,
                club_speed_mph=club_sp,
                smash_factor=_to_float(_get(row, "smash_factor")),
                launch_angle_vertical=_to_float(
                    _get(row, "launch_angle_vertical")),
                launch_angle_horizontal=_to_float(
                    _get(row, "launch_angle_horizontal")),
                spin_rpm=_to_float(_get(row, "spin_rpm")),
                carry_yards=carry,
                raw=dict(row),
            ))
    return shots


# ---------------------------------------------------------------------------
# Pairing
# ---------------------------------------------------------------------------

@dataclass
class Pair:
    of: Optional[Shot]
    tm: Optional[Shot]
    match_quality: str  # "good" | "ball_speed_mismatch" | "unmatched_openflight" | "unmatched_trackman"
    notes: str = ""


def _sort_for_pairing(shots: Iterable[Shot]) -> List[Shot]:
    """Order shots for chronological pairing. Prefer timestamp; fall
    back to shot_number; preserve input order otherwise (stable)."""
    def key(s: Shot, idx: int) -> Tuple:
        ts = s.timestamp.timestamp() if s.timestamp else float("inf")
        sn = s.shot_number if s.shot_number is not None else float("inf")
        return (ts, sn, idx)
    indexed = list(enumerate(shots))
    indexed.sort(key=lambda item: key(item[1], item[0]))
    return [s for _, s in indexed]


def pair_shots(
    of_shots: List[Shot],
    tm_shots: List[Shot],
    ball_speed_tol_mph: float = 5.0,
    club_filter: Optional[List[str]] = None,
) -> List[Pair]:
    """Pair OpenFlight ↔ Trackman shots in chronological order within
    each club. Pairs whose ball-speed delta exceeds the tolerance are
    flagged ``ball_speed_mismatch`` (still emitted so you can fix
    alignment by hand).
    """
    pairs: List[Pair] = []

    of_by_club: Dict[str, List[Shot]] = {}
    tm_by_club: Dict[str, List[Shot]] = {}
    for s in of_shots:
        of_by_club.setdefault(s.club, []).append(s)
    for s in tm_shots:
        tm_by_club.setdefault(s.club, []).append(s)

    clubs = set(of_by_club) | set(tm_by_club)
    if club_filter:
        wanted = {normalize_club(c) for c in club_filter}
        clubs &= wanted

    # Stable, friendly ordering — driver first, then irons by number, then wedges.
    def club_sort_key(c: str) -> Tuple:
        if c == "driver": return (0, 0, c)
        m = re.match(r"(\d+)-(wood|hybrid|iron)", c)
        if m:
            ord_map = {"wood": 1, "hybrid": 2, "iron": 3}
            return (ord_map[m.group(2)], int(m.group(1)), c)
        if c in ("pw", "gw", "sw", "lw"):
            return (4, ["pw","gw","sw","lw"].index(c), c)
        return (5, 0, c)

    for club in sorted(clubs, key=club_sort_key):
        of_seq = _sort_for_pairing(of_by_club.get(club, []))
        tm_seq = _sort_for_pairing(tm_by_club.get(club, []))
        i = j = 0
        while i < len(of_seq) and j < len(tm_seq):
            of_s, tm_s = of_seq[i], tm_seq[j]
            mq = "good"
            notes = ""
            if (of_s.ball_speed_mph is not None
                    and tm_s.ball_speed_mph is not None):
                d = abs(of_s.ball_speed_mph - tm_s.ball_speed_mph)
                if d > ball_speed_tol_mph:
                    mq = "ball_speed_mismatch"
                    notes = (f"ball-speed delta {d:.1f} mph "
                             f"exceeds tol {ball_speed_tol_mph} mph; "
                             f"check pairing manually")
            pairs.append(Pair(of=of_s, tm=tm_s,
                              match_quality=mq, notes=notes))
            i += 1
            j += 1

        # Trailing unmatched shots from either side — keep so the user
        # can see where alignment ran off.
        for k in range(i, len(of_seq)):
            pairs.append(Pair(of=of_seq[k], tm=None,
                              match_quality="unmatched_openflight",
                              notes="no Trackman shot for this club position"))
        for k in range(j, len(tm_seq)):
            pairs.append(Pair(of=None, tm=tm_seq[k],
                              match_quality="unmatched_trackman",
                              notes="no OpenFlight shot for this club position"))

    return pairs


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

_OUTPUT_FIELDS = [
    "shot_number_of", "shot_number_tm",
    "timestamp_of", "timestamp_tm",
    "club",
    "ball_speed_of", "ball_speed_tm", "ball_speed_delta",
    "club_speed_of", "club_speed_tm", "club_speed_delta",
    "smash_of", "smash_tm", "smash_delta",
    "launch_v_of", "launch_v_tm", "launch_v_delta",
    "launch_h_of", "launch_h_tm", "launch_h_delta",
    "spin_of", "spin_tm", "spin_delta",
    "carry_of", "carry_tm", "carry_delta",
    "match_quality", "notes",
]


def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return round(a - b, 3)


def _row(pair: Pair) -> Dict[str, Any]:
    of, tm = pair.of, pair.tm
    def f(val: Any) -> Any:
        if isinstance(val, float):
            return round(val, 3)
        return val
    return {
        "shot_number_of":   f(of.shot_number) if of else None,
        "shot_number_tm":   f(tm.shot_number) if tm else None,
        "timestamp_of":     of.timestamp.isoformat() if of and of.timestamp else None,
        "timestamp_tm":     tm.timestamp.isoformat() if tm and tm.timestamp else None,
        "club":             (of or tm).club if (of or tm) else "",
        "ball_speed_of":    f(of.ball_speed_mph) if of else None,
        "ball_speed_tm":    f(tm.ball_speed_mph) if tm else None,
        "ball_speed_delta": _delta(of.ball_speed_mph if of else None,
                                   tm.ball_speed_mph if tm else None),
        "club_speed_of":    f(of.club_speed_mph) if of else None,
        "club_speed_tm":    f(tm.club_speed_mph) if tm else None,
        "club_speed_delta": _delta(of.club_speed_mph if of else None,
                                   tm.club_speed_mph if tm else None),
        "smash_of":         f(of.smash_factor) if of else None,
        "smash_tm":         f(tm.smash_factor) if tm else None,
        "smash_delta":      _delta(of.smash_factor if of else None,
                                   tm.smash_factor if tm else None),
        "launch_v_of":      f(of.launch_angle_vertical) if of else None,
        "launch_v_tm":      f(tm.launch_angle_vertical) if tm else None,
        "launch_v_delta":   _delta(of.launch_angle_vertical if of else None,
                                   tm.launch_angle_vertical if tm else None),
        "launch_h_of":      f(of.launch_angle_horizontal) if of else None,
        "launch_h_tm":      f(tm.launch_angle_horizontal) if tm else None,
        "launch_h_delta":   _delta(of.launch_angle_horizontal if of else None,
                                   tm.launch_angle_horizontal if tm else None),
        "spin_of":          f(of.spin_rpm) if of else None,
        "spin_tm":          f(tm.spin_rpm) if tm else None,
        "spin_delta":       _delta(of.spin_rpm if of else None,
                                   tm.spin_rpm if tm else None),
        "carry_of":         f(of.carry_yards) if of else None,
        "carry_tm":         f(tm.carry_yards) if tm else None,
        "carry_delta":      _delta(of.carry_yards if of else None,
                                   tm.carry_yards if tm else None),
        "match_quality":    pair.match_quality,
        "notes":            pair.notes,
    }


def write_comparison_csv(pairs: List[Pair], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_OUTPUT_FIELDS)
        writer.writeheader()
        for p in pairs:
            writer.writerow(_row(p))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

_DELTA_LABELS = [
    ("ball_speed_delta", "ball speed",  "mph"),
    ("club_speed_delta", "club speed",  "mph"),
    ("launch_v_delta",   "launch V",    "deg"),
    ("launch_h_delta",   "launch H",    "deg"),
    ("spin_delta",       "spin",        "rpm"),
    ("carry_delta",      "carry",       "yds"),
]


def print_summary(pairs: List[Pair]) -> None:
    rows = [_row(p) for p in pairs]
    by_club: Dict[str, List[Dict[str, Any]]] = {}
    counts = {"good": 0, "ball_speed_mismatch": 0,
              "unmatched_openflight": 0, "unmatched_trackman": 0}
    for r in rows:
        counts[r["match_quality"]] = counts.get(r["match_quality"], 0) + 1
        by_club.setdefault(r["club"] or "(no club)", []).append(r)

    print()
    print("=" * 72)
    print("  COMPARISON SUMMARY")
    print("=" * 72)
    print(f"  Total pairs:           {len(rows)}")
    print(f"  Good:                  {counts['good']}")
    print(f"  Ball-speed mismatch:   {counts['ball_speed_mismatch']}")
    print(f"  Unmatched OpenFlight:  {counts['unmatched_openflight']}")
    print(f"  Unmatched Trackman:    {counts['unmatched_trackman']}")
    print()

    for club in sorted(by_club):
        good = [r for r in by_club[club] if r["match_quality"] == "good"]
        if not good:
            print(f"  {club}: no good pairs ({len(by_club[club])} total)")
            continue
        print(f"  {club} — {len(good)} good pair(s) "
              f"(of {len(by_club[club])} total)")
        print(f"    {'metric':<12}  {'mean Δ (of-tm)':>15}  "
              f"{'stddev':>10}  {'|max|':>8}")
        for key, label, unit in _DELTA_LABELS:
            vals = [r[key] for r in good if r[key] is not None]
            if not vals:
                continue
            mean = statistics.fmean(vals)
            sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
            mx = max(vals, key=abs)
            print(f"    {label:<12}  {mean:>+12.2f} {unit:<3}  "
                  f"{sd:>9.2f}  {mx:>+7.2f}")
        print()
    print("=" * 72)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pair OpenFlight ↔ Trackman shots and emit a "
                    "side-by-side comparison CSV.",
    )
    parser.add_argument("--openflight", required=True, type=Path,
                        help="OpenFlight session JSONL file")
    parser.add_argument("--trackman", required=True, type=Path,
                        help="Trackman CSV export")
    parser.add_argument("--output", required=True, type=Path,
                        help="Output comparison CSV")
    parser.add_argument("--ball-speed-tol", type=float, default=5.0,
                        help="Max ball-speed delta (mph) before a pair "
                             "is flagged as a likely mis-pair (default 5.0)")
    parser.add_argument("--club-filter", default=None,
                        help="Comma-separated list of clubs to include "
                             "(e.g. '7-iron,driver'). Default: all.")
    args = parser.parse_args(argv)

    if not args.openflight.exists():
        print(f"OpenFlight log not found: {args.openflight}", file=sys.stderr)
        return 2
    if not args.trackman.exists():
        print(f"Trackman CSV not found: {args.trackman}", file=sys.stderr)
        return 2

    of_shots = load_openflight(args.openflight)
    tm_shots = load_trackman(args.trackman)
    print(f"Loaded {len(of_shots)} OpenFlight shots, "
          f"{len(tm_shots)} Trackman shots")

    club_filter = (
        [c.strip() for c in args.club_filter.split(",") if c.strip()]
        if args.club_filter else None
    )
    pairs = pair_shots(of_shots, tm_shots,
                       ball_speed_tol_mph=args.ball_speed_tol,
                       club_filter=club_filter)
    write_comparison_csv(pairs, args.output)
    print(f"Wrote {len(pairs)} pair rows to {args.output}")
    print_summary(pairs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
