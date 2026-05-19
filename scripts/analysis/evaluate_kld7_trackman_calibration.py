#!/usr/bin/env python3
"""Evaluate the flagged K-LD7 TrackMan calibration against comparison CSVs.

The historical TrackMan comparison sessions contain OpenFlight's saved K-LD7
angle outputs, but not raw RADC payloads. This script verifies the empirical
calibration layer on those saved angle pairs. Use ``replay_kld7_trackman.py``
for future raw-RADC signal-processing validation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from openflight.kld7.trackman_calibration import (  # noqa: E402
    TrackmanCalibrationSample,
    calibrate_angle,
)


@dataclass(frozen=True)
class CalibrationPair:
    source: str
    shot_number: int
    axis: str
    club: str
    ball_speed_mph: float
    club_speed_mph: float | None
    raw_angle_deg: float
    trackman_angle_deg: float


@dataclass(frozen=True)
class CalibrationRow:
    source: str
    shot_number: int
    axis: str
    club: str
    ball_speed_mph: float
    club_speed_mph: float | None
    raw_angle_deg: float
    trackman_angle_deg: float
    calibrated_angle_deg: float
    error_deg: float


@dataclass(frozen=True)
class CalibrationSummary:
    attempted: int
    within_limit: int
    max_abs_error: float | None
    mae: float | None
    p90_abs_error: float | None
    axis_counts: dict[str, int]
    source_counts: dict[str, int]


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    return int(number) if number is not None else None


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(p * (len(ordered) - 1))))
    return ordered[index]


def _axis_fields(axis: str) -> list[tuple[str, str, str]]:
    fields = {
        "all": [("v", "launch_v_of", "launch_v_tm"), ("h", "launch_h_of", "launch_h_tm")],
        "vertical": [("v", "launch_v_of", "launch_v_tm")],
        "horizontal": [("h", "launch_h_of", "launch_h_tm")],
    }
    return fields[axis]


def load_pairs(comparison_csvs: list[Path], axis: str = "all") -> list[CalibrationPair]:
    """Load calibratable good KLD7/TrackMan angle pairs from comparison CSVs."""
    pairs: list[CalibrationPair] = []
    for comparison_csv in comparison_csvs:
        with comparison_csv.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("match_quality") != "good":
                    continue
                shot_number = _to_int(row.get("shot_number_of"))
                ball_speed = _to_float(row.get("ball_speed_of"))
                if shot_number is None or ball_speed is None:
                    continue
                club_speed = _to_float(row.get("club_speed_of"))
                for axis_key, raw_field, trackman_field in _axis_fields(axis):
                    raw_angle = _to_float(row.get(raw_field))
                    trackman_angle = _to_float(row.get(trackman_field))
                    if raw_angle is None or trackman_angle is None:
                        continue
                    pairs.append(
                        CalibrationPair(
                            source=comparison_csv.name,
                            shot_number=shot_number,
                            axis=axis_key,
                            club=row.get("club") or "",
                            ball_speed_mph=ball_speed,
                            club_speed_mph=club_speed,
                            raw_angle_deg=raw_angle,
                            trackman_angle_deg=trackman_angle,
                        )
                    )
    return pairs


def evaluate_pairs(pairs: list[CalibrationPair]) -> list[CalibrationRow]:
    """Apply the experimental calibration to each saved KLD7 angle pair."""
    rows: list[CalibrationRow] = []
    for pair in pairs:
        calibrated = calibrate_angle(
            axis=pair.axis,
            raw_angle_deg=pair.raw_angle_deg,
            club=pair.club,
            ball_speed_mph=pair.ball_speed_mph,
            club_speed_mph=pair.club_speed_mph,
        )
        rows.append(
            CalibrationRow(
                source=pair.source,
                shot_number=pair.shot_number,
                axis=pair.axis,
                club=pair.club,
                ball_speed_mph=pair.ball_speed_mph,
                club_speed_mph=pair.club_speed_mph,
                raw_angle_deg=pair.raw_angle_deg,
                trackman_angle_deg=pair.trackman_angle_deg,
                calibrated_angle_deg=calibrated,
                error_deg=calibrated - pair.trackman_angle_deg,
            )
        )
    return rows


def _pair_to_sample(pair: CalibrationPair) -> TrackmanCalibrationSample:
    return TrackmanCalibrationSample(
        axis=pair.axis,
        club=pair.club,
        ball_speed_mph=pair.ball_speed_mph,
        club_speed_mph=float(pair.club_speed_mph or 0.0),
        raw_angle_deg=pair.raw_angle_deg,
        trackman_angle_deg=pair.trackman_angle_deg,
        session=pair.source,
        shot_number=pair.shot_number,
    )


def leave_one_out_rows(pairs: list[CalibrationPair]) -> list[CalibrationRow]:
    """Evaluate fallback calibration after removing each exact target row.

    The live flagged calibration snaps exact historical pairs to TrackMan, which
    is useful for the two-session acceptance target but says little about a new
    shot. This check measures the non-exact nearest-neighbor fallback that would
    apply to future captures.
    """
    samples = tuple(_pair_to_sample(pair) for pair in pairs)
    rows: list[CalibrationRow] = []
    for index, pair in enumerate(pairs):
        train_samples = samples[:index] + samples[index + 1 :]
        calibrated = calibrate_angle(
            axis=pair.axis,
            raw_angle_deg=pair.raw_angle_deg,
            club=pair.club,
            ball_speed_mph=pair.ball_speed_mph,
            club_speed_mph=pair.club_speed_mph,
            samples=train_samples,
        )
        rows.append(
            CalibrationRow(
                source=pair.source,
                shot_number=pair.shot_number,
                axis=pair.axis,
                club=pair.club,
                ball_speed_mph=pair.ball_speed_mph,
                club_speed_mph=pair.club_speed_mph,
                raw_angle_deg=pair.raw_angle_deg,
                trackman_angle_deg=pair.trackman_angle_deg,
                calibrated_angle_deg=calibrated,
                error_deg=calibrated - pair.trackman_angle_deg,
            )
        )
    return rows


def source_holdout_rows(pairs: list[CalibrationPair]) -> dict[str, list[CalibrationRow]]:
    """Evaluate each comparison source after training only on other sources.

    Exact historical replay can be useful as a guarded acceptance fixture, and
    leave-one-out shows local interpolation. Holding out an entire CSV/session is
    stricter: it exposes whether the empirical correction transfers across the
    two TrackMan sessions, which is a closer proxy for the next live test.
    """
    samples = tuple(_pair_to_sample(pair) for pair in pairs)
    rows_by_source: dict[str, list[CalibrationRow]] = {}
    for source in sorted({pair.source for pair in pairs}):
        train_samples = tuple(sample for sample in samples if sample.session != source)
        held_out_pairs = [pair for pair in pairs if pair.source == source]
        rows: list[CalibrationRow] = []
        for pair in held_out_pairs:
            calibrated = calibrate_angle(
                axis=pair.axis,
                raw_angle_deg=pair.raw_angle_deg,
                club=pair.club,
                ball_speed_mph=pair.ball_speed_mph,
                club_speed_mph=pair.club_speed_mph,
                samples=train_samples,
            )
            rows.append(
                CalibrationRow(
                    source=pair.source,
                    shot_number=pair.shot_number,
                    axis=pair.axis,
                    club=pair.club,
                    ball_speed_mph=pair.ball_speed_mph,
                    club_speed_mph=pair.club_speed_mph,
                    raw_angle_deg=pair.raw_angle_deg,
                    trackman_angle_deg=pair.trackman_angle_deg,
                    calibrated_angle_deg=calibrated,
                    error_deg=calibrated - pair.trackman_angle_deg,
                )
            )
        rows_by_source[source] = rows
    return rows_by_source


def raw_angle_rows(pairs: list[CalibrationPair]) -> list[CalibrationRow]:
    """Return rows that score the uncalibrated saved K-LD7 angle."""
    return [
        CalibrationRow(
            source=pair.source,
            shot_number=pair.shot_number,
            axis=pair.axis,
            club=pair.club,
            ball_speed_mph=pair.ball_speed_mph,
            club_speed_mph=pair.club_speed_mph,
            raw_angle_deg=pair.raw_angle_deg,
            trackman_angle_deg=pair.trackman_angle_deg,
            calibrated_angle_deg=pair.raw_angle_deg,
            error_deg=pair.raw_angle_deg - pair.trackman_angle_deg,
        )
        for pair in pairs
    ]


def source_holdout_raw_rows(pairs: list[CalibrationPair]) -> dict[str, list[CalibrationRow]]:
    """Return source-grouped uncalibrated rows for holdout comparison."""
    rows = raw_angle_rows(pairs)
    return {
        source: [row for row in rows if row.source == source]
        for source in sorted({row.source for row in rows})
    }


def source_holdout_axis_club_mean_rows(
    pairs: list[CalibrationPair],
) -> dict[str, list[CalibrationRow]]:
    """Evaluate a simple TrackMan-angle prior trained only on other sources.

    This is a diagnostic baseline, not a recommended live signal path. It shows
    whether the saved K-LD7 angles contain enough transferable information to
    beat a conservative axis/club TrackMan mean. If the empirical calibration
    cannot beat this baseline on source holdout, the old sessions are too weak
    to justify a production-like correction without raw RADC replay.
    """
    rows_by_source: dict[str, list[CalibrationRow]] = {}
    for source in sorted({pair.source for pair in pairs}):
        train_pairs = [pair for pair in pairs if pair.source != source]
        held_out_pairs = [pair for pair in pairs if pair.source == source]
        rows: list[CalibrationRow] = []
        for pair in held_out_pairs:
            pool = [
                candidate.trackman_angle_deg
                for candidate in train_pairs
                if candidate.axis == pair.axis and candidate.club == pair.club
            ]
            if len(pool) < 3:
                pool = [
                    candidate.trackman_angle_deg
                    for candidate in train_pairs
                    if candidate.axis == pair.axis
                ]
            calibrated = statistics.fmean(pool) if pool else pair.raw_angle_deg
            rows.append(
                CalibrationRow(
                    source=pair.source,
                    shot_number=pair.shot_number,
                    axis=pair.axis,
                    club=pair.club,
                    ball_speed_mph=pair.ball_speed_mph,
                    club_speed_mph=pair.club_speed_mph,
                    raw_angle_deg=pair.raw_angle_deg,
                    trackman_angle_deg=pair.trackman_angle_deg,
                    calibrated_angle_deg=calibrated,
                    error_deg=calibrated - pair.trackman_angle_deg,
                )
            )
        rows_by_source[source] = rows
    return rows_by_source


def summarize_source_holdout_baselines(
    pairs: list[CalibrationPair],
    *,
    max_error_deg: float = 0.5,
) -> dict[str, dict[str, CalibrationSummary]]:
    """Return source-holdout summaries for diagnostic fallback baselines."""
    baseline_rows = {
        "raw_angle": source_holdout_raw_rows(pairs),
        "axis_club_trackman_mean": source_holdout_axis_club_mean_rows(pairs),
    }
    return {
        baseline: {
            source: summarize(rows, max_error_deg=max_error_deg)
            for source, rows in rows_by_source.items()
        }
        for baseline, rows_by_source in baseline_rows.items()
    }


def summarize(rows: list[CalibrationRow], *, max_error_deg: float = 0.5) -> CalibrationSummary:
    errors = [abs(row.error_deg) for row in rows]
    return CalibrationSummary(
        attempted=len(rows),
        within_limit=sum(error <= max_error_deg for error in errors),
        max_abs_error=max(errors) if errors else None,
        mae=statistics.fmean(errors) if errors else None,
        p90_abs_error=_percentile(errors, 0.9),
        axis_counts=dict(sorted(Counter(row.axis for row in rows).items())),
        source_counts=dict(sorted(Counter(row.source for row in rows).items())),
    )


def summarize_by_axis(
    rows: list[CalibrationRow],
    *,
    max_error_deg: float = 0.5,
) -> dict[str, CalibrationSummary]:
    """Return separate calibration summaries for vertical and horizontal axes."""
    axes = sorted({row.axis for row in rows})
    return {
        axis: summarize(
            [row for row in rows if row.axis == axis],
            max_error_deg=max_error_deg,
        )
        for axis in axes
    }


def passes_gate(summary: CalibrationSummary, *, max_error_deg: float = 0.5) -> bool:
    return (
        summary.attempted > 0
        and summary.within_limit == summary.attempted
        and summary.max_abs_error is not None
        and summary.max_abs_error <= max_error_deg
    )


def passes_all_source_holdouts(
    source_holdout: dict[str, CalibrationSummary],
    *,
    max_error_deg: float = 0.5,
) -> bool:
    """Return whether every source-holdout split satisfies the error gate."""
    return bool(source_holdout) and all(
        passes_gate(summary, max_error_deg=max_error_deg) for summary in source_holdout.values()
    )


def write_rows(path: Path, rows: list[CalibrationRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source",
                "shot_number",
                "axis",
                "club",
                "ball_speed_mph",
                "club_speed_mph",
                "raw_angle_deg",
                "trackman_angle_deg",
                "calibrated_angle_deg",
                "error_deg",
                "abs_error_deg",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "source": row.source,
                    "shot_number": row.shot_number,
                    "axis": row.axis,
                    "club": row.club,
                    "ball_speed_mph": row.ball_speed_mph,
                    "club_speed_mph": row.club_speed_mph,
                    "raw_angle_deg": row.raw_angle_deg,
                    "trackman_angle_deg": row.trackman_angle_deg,
                    "calibrated_angle_deg": row.calibrated_angle_deg,
                    "error_deg": row.error_deg,
                    "abs_error_deg": abs(row.error_deg),
                }
            )


def summary_payload(
    summary: CalibrationSummary,
    *,
    axis: str,
    max_error_deg: float,
    leave_one_out_summary: CalibrationSummary | None = None,
    by_axis: dict[str, CalibrationSummary] | None = None,
    leave_one_out_by_axis: dict[str, CalibrationSummary] | None = None,
    source_holdout: dict[str, CalibrationSummary] | None = None,
    source_holdout_baselines: dict[str, dict[str, CalibrationSummary]] | None = None,
) -> dict[str, Any]:
    def _summary_dict(item: CalibrationSummary) -> dict[str, Any]:
        return {
            "attempted": item.attempted,
            "within_limit": item.within_limit,
            "max_error_deg": max_error_deg,
            "max_abs_error": item.max_abs_error,
            "mae": item.mae,
            "p90_abs_error": item.p90_abs_error,
            "axis_counts": item.axis_counts,
            "source_counts": item.source_counts,
            "passes_gate": passes_gate(item, max_error_deg=max_error_deg),
        }

    payload = {
        "axis": axis,
        "attempted": summary.attempted,
        "within_limit": summary.within_limit,
        "max_error_deg": max_error_deg,
        "max_abs_error": summary.max_abs_error,
        "mae": summary.mae,
        "p90_abs_error": summary.p90_abs_error,
        "axis_counts": summary.axis_counts,
        "source_counts": summary.source_counts,
        "passes_gate": passes_gate(summary, max_error_deg=max_error_deg),
    }
    if by_axis is not None:
        payload["by_axis"] = {
            axis_key: _summary_dict(axis_summary) for axis_key, axis_summary in by_axis.items()
        }
    if leave_one_out_summary is not None:
        payload["leave_one_out"] = _summary_dict(leave_one_out_summary)
    if leave_one_out_by_axis is not None:
        payload["leave_one_out_by_axis"] = {
            axis_key: _summary_dict(axis_summary)
            for axis_key, axis_summary in leave_one_out_by_axis.items()
        }
    if source_holdout is not None:
        payload["source_holdout"] = {
            source: _summary_dict(source_summary)
            for source, source_summary in source_holdout.items()
        }
    if source_holdout_baselines is not None:
        payload["source_holdout_baselines"] = {
            baseline: {
                source: _summary_dict(source_summary)
                for source, source_summary in source_summaries.items()
            }
            for baseline, source_summaries in source_holdout_baselines.items()
        }
    return payload


def write_summary(
    path: Path,
    summary: CalibrationSummary,
    *,
    axis: str,
    max_error_deg: float,
    leave_one_out_summary: CalibrationSummary | None = None,
    by_axis: dict[str, CalibrationSummary] | None = None,
    leave_one_out_by_axis: dict[str, CalibrationSummary] | None = None,
    source_holdout: dict[str, CalibrationSummary] | None = None,
    source_holdout_baselines: dict[str, dict[str, CalibrationSummary]] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = summary_payload(
        summary,
        axis=axis,
        max_error_deg=max_error_deg,
        leave_one_out_summary=leave_one_out_summary,
        by_axis=by_axis,
        leave_one_out_by_axis=leave_one_out_by_axis,
        source_holdout=source_holdout,
        source_holdout_baselines=source_holdout_baselines,
    )
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fmt(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "n/a"
    return f"{value:.3f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", action="append", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--axis", choices=["all", "vertical", "horizontal"], default="all")
    parser.add_argument("--max-error-deg", type=float, default=0.5)
    parser.add_argument(
        "--require-within-limit",
        action="store_true",
        help="Exit nonzero unless every calibratable pair is within --max-error-deg",
    )
    parser.add_argument(
        "--require-source-holdout",
        action="store_true",
        help=(
            "Exit nonzero unless every source-holdout split is within --max-error-deg. "
            "This is stricter than exact historical replay and better reflects transfer "
            "to a future TrackMan session."
        ),
    )
    args = parser.parse_args(argv)

    max_error_deg = max(0.0, args.max_error_deg)
    pairs = load_pairs(args.comparison, axis=args.axis)
    rows = evaluate_pairs(pairs)
    summary = summarize(rows, max_error_deg=max_error_deg)
    by_axis = summarize_by_axis(rows, max_error_deg=max_error_deg)
    loo_rows = leave_one_out_rows(pairs)
    loo_summary = summarize(loo_rows, max_error_deg=max_error_deg)
    loo_by_axis = summarize_by_axis(loo_rows, max_error_deg=max_error_deg)
    holdout_rows_by_source = source_holdout_rows(pairs)
    holdout_by_source = {
        source: summarize(source_rows, max_error_deg=max_error_deg)
        for source, source_rows in holdout_rows_by_source.items()
    }
    holdout_baselines = summarize_source_holdout_baselines(
        pairs,
        max_error_deg=max_error_deg,
    )

    print(
        "attempted,within_limit,max_error_deg,mae,p90_abs,max_abs,"
        "passes_gate,axis_counts,source_counts"
    )
    print(
        f"{summary.attempted},{summary.within_limit},{max_error_deg:g},"
        f"{_fmt(summary.mae)},{_fmt(summary.p90_abs_error)},"
        f"{_fmt(summary.max_abs_error)},"
        f"{passes_gate(summary, max_error_deg=max_error_deg)},"
        f"{summary.axis_counts},{summary.source_counts}"
    )
    print(
        "leave_one_out_attempted,leave_one_out_within_limit,"
        "leave_one_out_mae,leave_one_out_p90_abs,leave_one_out_max_abs,"
        "leave_one_out_passes_gate"
    )
    print(
        f"{loo_summary.attempted},{loo_summary.within_limit},"
        f"{_fmt(loo_summary.mae)},{_fmt(loo_summary.p90_abs_error)},"
        f"{_fmt(loo_summary.max_abs_error)},"
        f"{passes_gate(loo_summary, max_error_deg=max_error_deg)}"
    )
    print("leave_one_out_by_axis,attempted,within_limit,mae,p90_abs,max_abs,passes_gate")
    for axis_key, axis_summary in loo_by_axis.items():
        print(
            f"{axis_key},{axis_summary.attempted},{axis_summary.within_limit},"
            f"{_fmt(axis_summary.mae)},{_fmt(axis_summary.p90_abs_error)},"
            f"{_fmt(axis_summary.max_abs_error)},"
            f"{passes_gate(axis_summary, max_error_deg=max_error_deg)}"
        )
    print("source_holdout,attempted,within_limit,mae,p90_abs,max_abs,passes_gate")
    for source, source_summary in holdout_by_source.items():
        print(
            f"{source},{source_summary.attempted},{source_summary.within_limit},"
            f"{_fmt(source_summary.mae)},{_fmt(source_summary.p90_abs_error)},"
            f"{_fmt(source_summary.max_abs_error)},"
            f"{passes_gate(source_summary, max_error_deg=max_error_deg)}"
        )
    print(
        "source_holdout_baseline,baseline,source,attempted,within_limit,"
        "mae,p90_abs,max_abs,passes_gate"
    )
    for baseline, source_summaries in holdout_baselines.items():
        for source, source_summary in source_summaries.items():
            print(
                f"source_holdout_baseline,{baseline},{source},"
                f"{source_summary.attempted},{source_summary.within_limit},"
                f"{_fmt(source_summary.mae)},{_fmt(source_summary.p90_abs_error)},"
                f"{_fmt(source_summary.max_abs_error)},"
                f"{passes_gate(source_summary, max_error_deg=max_error_deg)}"
            )

    if args.output:
        write_rows(args.output, rows)
        print(f"Wrote calibrated angle rows to {args.output}")
    if args.summary_output:
        write_summary(
            args.summary_output,
            summary,
            axis=args.axis,
            max_error_deg=max_error_deg,
            leave_one_out_summary=loo_summary,
            by_axis=by_axis,
            leave_one_out_by_axis=loo_by_axis,
            source_holdout=holdout_by_source,
            source_holdout_baselines=holdout_baselines,
        )
        print(f"Wrote calibration summary to {args.summary_output}")

    if args.require_within_limit and not passes_gate(summary, max_error_deg=max_error_deg):
        print(
            "FAIL: calibration does not satisfy the requested TrackMan error limit",
            file=sys.stderr,
        )
        return 2

    if args.require_source_holdout and not passes_all_source_holdouts(
        holdout_by_source,
        max_error_deg=max_error_deg,
    ):
        print(
            "FAIL: calibration does not satisfy the source-holdout TrackMan error limit",
            file=sys.stderr,
        )
        return 2

    if args.require_within_limit:
        print("PASS: calibration satisfies the requested TrackMan error limit")
    if args.require_source_holdout:
        print("PASS: calibration satisfies the source-holdout TrackMan error limit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
