#!/usr/bin/env python3
"""Diagnose horizontal launch angle inconsistency from session logs.

Two complementary modes:

1. JSONL session log mode (default).
   Mines `shot_detected` and `kld7_buffer` events to characterize how the
   horizontal radar's angle output behaves shot-to-shot. This mode cannot
   replay the FFT pipeline because the live tracker strips raw RADC bytes
   from snapshot_buffer (see KLD7Tracker.snapshot_buffer). It uses the live
   diagnostics that ARE logged: per-shot ball_angle (horizontal_deg,
   confidence, magnitude/SNR, num_frames), per-frame timestamps, and
   downstream Shot fields.

2. RADC capture mode (--radc PATH).
   Operates on `.pkl` files produced by scripts/analysis/capture_kld7_radc.py
   which DO contain raw 3072-byte RADC frames. In this mode we re-run the
   real `extract_launch_angle` pipeline per shot, plus a per-frame breakdown
   of the ball-band spectrum, picked peak bin, per-bin angle, and SNR. This
   is the right tool to confirm whether the horizontal radar's peak-bin
   selection is locking onto the ball or onto club/multipath/sidelobes.

Usage:
    # JSONL mode
    python scripts/analysis/diagnose_horizontal_angle.py \\
        session_logs/session_2026042[12]_*_range.jsonl \\
        --output-dir session_logs/h_angle_diag

    # RADC capture mode
    python scripts/analysis/diagnose_horizontal_angle.py \\
        --radc session_logs/kld7_radc_20260406_161627-7i.pkl \\
        --output-dir session_logs/radc_diag
"""

from __future__ import annotations

import argparse
import json
import statistics as stats
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

C_FACE = "#9C27B0"
C_PATH = "#FF9800"
C_DIFF = "#F44336"
C_GRID = "#cccccc"


# ---------- data model ----------


@dataclass
class ShotRow:
    session_id: str
    shot_number: int
    ts: str
    ball_speed_mph: Optional[float]
    club_speed_mph: Optional[float]
    angle_source: Optional[str]
    h_angle: Optional[float]
    v_angle: Optional[float]
    confidence: Optional[float]
    club_path_deg: Optional[float]
    spin_axis_deg: Optional[float]
    # From horizontal kld7_buffer (live diagnostics)
    h_ball_angle: Optional[float] = None
    h_confidence: Optional[float] = None
    h_num_frames: Optional[int] = None
    h_avg_snr_db: Optional[float] = None
    h_buffer_frame_count: Optional[int] = None  # total frames in ring buffer
    h_buffer_span_s: Optional[float] = None     # time span across buffer
    # From vertical kld7_buffer
    v_buffer_frame_count: Optional[int] = None
    v_ball_angle: Optional[float] = None
    v_confidence: Optional[float] = None


def load_sessions(paths: list[Path]) -> list[ShotRow]:
    rows: list[ShotRow] = []
    for p in paths:
        sid = p.stem.replace("_range", "")
        shots_by_num: dict[int, ShotRow] = {}
        # Buffer kld7_buffer entries (they appear before shot_detected in the log)
        # keyed by (shot_number, orientation) -> dict of fields
        pending_bufs: dict[tuple[int, str], dict] = {}

        def buf_fields(entry: dict) -> dict:
            frames = entry.get("frames") or []
            fc = len(frames)
            span = None
            if fc >= 2:
                ts_list = [f.get("timestamp") for f in frames
                           if isinstance(f.get("timestamp"), (int, float))]
                if len(ts_list) >= 2:
                    span = max(ts_list) - min(ts_list)
            ba = entry.get("ball_angle") or {}
            return {
                "frame_count": fc,
                "span_s": span,
                "ball_angle": ba,
            }

        def apply_buf(row: ShotRow, orientation: str, fields: dict) -> None:
            ba = fields["ball_angle"]
            if orientation == "horizontal":
                row.h_buffer_frame_count = fields["frame_count"]
                row.h_buffer_span_s = fields["span_s"]
                row.h_ball_angle = ba.get("horizontal_deg")
                row.h_confidence = ba.get("confidence")
                row.h_num_frames = ba.get("num_frames")
                row.h_avg_snr_db = ba.get("magnitude")
            elif orientation == "vertical":
                row.v_buffer_frame_count = fields["frame_count"]
                row.v_ball_angle = ba.get("vertical_deg")
                row.v_confidence = ba.get("confidence")

        with p.open() as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = e.get("type")
                if t == "shot_detected":
                    sn = e.get("shot_number")
                    row = ShotRow(
                        session_id=sid,
                        shot_number=sn,
                        ts=e.get("ts", ""),
                        ball_speed_mph=e.get("ball_speed_mph"),
                        club_speed_mph=e.get("club_speed_mph"),
                        angle_source=e.get("angle_source"),
                        h_angle=e.get("launch_angle_horizontal"),
                        v_angle=e.get("launch_angle_vertical"),
                        confidence=e.get("launch_angle_confidence"),
                        club_path_deg=e.get("club_path_deg"),
                        spin_axis_deg=e.get("spin_axis_deg"),
                    )
                    # Apply any buffered kld7_buffer entries we already saw
                    for orient in ("horizontal", "vertical"):
                        fields = pending_bufs.pop((sn, orient), None)
                        if fields is not None:
                            apply_buf(row, orient, fields)
                    shots_by_num[sn] = row
                elif t == "kld7_buffer":
                    sn = e.get("shot_number")
                    orient = e.get("orientation")
                    fields = buf_fields(e)
                    row = shots_by_num.get(sn)
                    if row is not None:
                        apply_buf(row, orient, fields)
                    else:
                        pending_bufs[(sn, orient)] = fields
        rows.extend(shots_by_num.values())
    return rows


# ---------- aggregate stats ----------


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
    return s[k]


def fmt_stat(name: str, xs: list[float]) -> str:
    if not xs:
        return f"{name}: no data"
    return (
        f"{name}: n={len(xs):4d}  mean={stats.mean(xs):+7.2f}  "
        f"stdev={stats.pstdev(xs):5.2f}  min={min(xs):+6.1f}  "
        f"p10={percentile(xs, 0.10):+6.1f}  p50={percentile(xs, 0.50):+6.1f}  "
        f"p90={percentile(xs, 0.90):+6.1f}  max={max(xs):+6.1f}"
    )


def print_summary(rows: list[ShotRow]) -> None:
    print("=" * 100)
    print(f"DIAGNOSTIC SUMMARY  —  {len(rows)} shots, "
          f"{len({r.session_id for r in rows})} sessions")
    print("=" * 100)

    h_radar = [r for r in rows if r.angle_source == "radar" and r.h_angle is not None]
    h_est = [r for r in rows if r.angle_source == "estimated" and r.h_angle is not None]
    h_camera = [r for r in rows if r.angle_source == "camera" and r.h_angle is not None]
    h_none = [r for r in rows if r.h_angle is None]

    print(f"angle_source: radar={len(h_radar)}  estimated={len(h_est)}  "
          f"camera={len(h_camera)}  none={len(h_none)}")
    print()

    # Detection rate of horizontal radar (h_buffer present but live_h missing)
    have_buf = sum(1 for r in rows if r.h_buffer_frame_count)
    have_live = sum(1 for r in rows if r.h_ball_angle is not None)
    print("Horizontal radar detection rate:")
    print(f"  shots with horizontal kld7 buffer logged: {have_buf}")
    print(f"  shots where live ball_angle was returned: {have_live}  "
          f"({have_live*100/max(1, have_buf):.1f}% of bufs)")
    miss = have_buf - have_live
    print(f"  shots where horizontal radar saw nothing: {miss}  "
          f"({miss*100/max(1, have_buf):.1f}%)")
    print()

    print(fmt_stat("h_angle ALL    ", [r.h_angle for r in rows if r.h_angle is not None]))
    print(fmt_stat("h_angle radar  ", [r.h_angle for r in h_radar]))
    if h_radar:
        absh = [abs(r.h_angle) for r in h_radar]
        wall_close = sum(1 for v in absh if v >= 14.0)
        wall_at = sum(1 for v in absh if v >= 14.9)
        print(f"   |h|>=14°: {wall_close} ({wall_close*100/len(absh):.1f}%)   "
              f"|h|>=14.9°: {wall_at}")
    print()

    # Confidence vs |h|
    print("Confidence vs |h_angle| (radar-sourced):")
    cb = defaultdict(list)
    for r in h_radar:
        if r.confidence is not None:
            cb[round(r.confidence, 1)].append(abs(r.h_angle))
    print(f"  {'conf':>6} {'n':>5} {'mean|h|':>9} {'stdev':>7} {'max':>7}")
    for k in sorted(cb):
        xs = cb[k]
        print(f"  {k:>6.1f} {len(xs):>5} {stats.mean(xs):>9.2f} "
              f"{stats.pstdev(xs):>7.2f} {max(xs):>7.1f}")
    print()

    # Shot-to-shot deltas
    print("Shot-to-shot |Δh_angle| (radar-sourced, same session):")
    deltas = []
    for sid in {r.session_id for r in h_radar}:
        seq = sorted([r for r in h_radar if r.session_id == sid],
                     key=lambda r: r.shot_number)
        for a, b in zip(seq, seq[1:]):
            deltas.append(abs(b.h_angle - a.h_angle))
    print("  " + fmt_stat("|delta|", deltas))
    print()

    # Face vs path
    pairs = [(r.h_angle, r.club_path_deg, r.spin_axis_deg)
             for r in rows
             if r.h_angle is not None and r.club_path_deg is not None]
    if pairs:
        diffs = [f - p for f, p, _ in pairs]
        print(f"Face vs path (radar): n={len(pairs)}  "
              f"mean(face-path)={stats.mean(diffs):+.2f}  "
              f"stdev={stats.pstdev(diffs):.2f}  "
              f"min={min(diffs):+.1f}  max={max(diffs):+.1f}")
        ext15 = sum(1 for d in diffs if abs(d) > 15.0)
        ext20 = sum(1 for d in diffs if abs(d) > 20.0)
        print(f"  |face - path| > 15°: {ext15} ({ext15*100/len(diffs):.1f}%)")
        print(f"  |face - path| > 20°: {ext20} ({ext20*100/len(diffs):.1f}%)")

        # corr
        xs = [p for _, p, _ in pairs]
        ys = [f for f, _, _ in pairs]
        if len(xs) >= 5 and stats.pstdev(xs) > 0 and stats.pstdev(ys) > 0:
            mx, my = stats.mean(xs), stats.mean(ys)
            cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / len(xs)
            r = cov / (stats.pstdev(xs) * stats.pstdev(ys))
            print(f"  corr(face, path) = {r:+.3f}  "
                  f"(near 0 = independent peaks; near 1 = same target)")
    print()

    # Per-session
    print("Per-session radar h_angle stats:")
    print(f"  {'session':<24}{'n':>4}{'detect%':>9}{'mean':>8}"
          f"{'stdev':>8}{'med|Δ|':>9}{'p90|Δ|':>9}")
    for sid in sorted({r.session_id for r in rows}):
        ses = [r for r in rows if r.session_id == sid]
        rad = [r for r in ses
               if r.angle_source == "radar" and r.h_angle is not None]
        if not rad:
            continue
        bufd = [r for r in ses if r.h_buffer_frame_count]
        live = [r for r in ses if r.h_ball_angle is not None]
        seq = sorted(rad, key=lambda r: r.shot_number)
        deltas = [abs(b.h_angle - a.h_angle) for a, b in zip(seq, seq[1:])]
        dr = (len(live) / len(bufd) * 100) if bufd else float("nan")
        med = percentile(deltas, 0.5) if deltas else float("nan")
        p90 = percentile(deltas, 0.9) if deltas else float("nan")
        print(f"  {sid:<24}{len(rad):>4}{dr:>8.1f}%"
              f"{stats.mean([r.h_angle for r in rad]):>+8.2f}"
              f"{stats.pstdev([r.h_angle for r in rad]):>8.2f}"
              f"{med:>9.2f}{p90:>9.2f}")
    print()


# ---------- plots ----------


def plot_distribution(rows: list[ShotRow], out_dir: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    h_radar = [r for r in rows
               if r.angle_source == "radar" and r.h_angle is not None]

    # 1) Histogram with ±15° wall
    ax = axes[0, 0]
    ax.hist([r.h_angle for r in h_radar],
            bins=np.arange(-16, 17, 1), color=C_FACE, edgecolor="k", alpha=0.8)
    ax.axvline(-15, color=C_DIFF, linestyle="--", label="±15° rejection wall")
    ax.axvline(15, color=C_DIFF, linestyle="--")
    ax.axvline(0, color="k", linewidth=0.5)
    ax.set_xlabel("horizontal launch angle (deg)")
    ax.set_ylabel("count")
    ax.set_title(f"Horizontal angle distribution (radar-sourced, n={len(h_radar)})")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=8)

    # 2) Confidence vs |h|
    ax = axes[0, 1]
    confs = [r.confidence for r in h_radar if r.confidence is not None]
    abs_h = [abs(r.h_angle) for r in h_radar if r.confidence is not None]
    ax.scatter(confs, abs_h, alpha=0.4, color=C_FACE, s=20)
    # binned mean overlay
    cb = defaultdict(list)
    for c, h in zip(confs, abs_h):
        cb[round(c, 1)].append(h)
    if cb:
        ks = sorted(cb)
        ax.plot(ks, [stats.mean(cb[k]) for k in ks],
                color=C_DIFF, marker="o", linewidth=2, label="binned mean")
        ax.legend()
    ax.set_xlabel("launch_angle_confidence")
    ax.set_ylabel("|h_angle| (deg)")
    ax.set_title("Confidence vs |h_angle|")
    ax.grid(alpha=0.3)

    # 3) Shot-to-shot |delta| sequence per session
    ax = axes[1, 0]
    sessions = sorted({r.session_id for r in h_radar})
    cmap = plt.get_cmap("tab10")
    for i, sid in enumerate(sessions):
        seq = sorted([r for r in h_radar if r.session_id == sid],
                     key=lambda r: r.shot_number)
        ds = [abs(b.h_angle - a.h_angle) for a, b in zip(seq, seq[1:])]
        if ds:
            ax.plot(ds, alpha=0.55, color=cmap(i % 10),
                    label=sid.replace("session_", ""))
    ax.set_xlabel("consecutive shot pair index")
    ax.set_ylabel("|Δ h_angle| (deg)")
    ax.set_title("Shot-to-shot volatility")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7, loc="upper right", ncol=2)

    # 4) face - path
    ax = axes[1, 1]
    diffs = [(r.h_angle - r.club_path_deg) for r in rows
             if r.h_angle is not None and r.club_path_deg is not None]
    ax.hist(diffs, bins=np.arange(-30, 31, 2), color=C_DIFF, edgecolor="k", alpha=0.8)
    ax.axvline(0, color="k", linewidth=0.5)
    ax.axvline(15, color="k", linestyle="--", alpha=0.5)
    ax.axvline(-15, color="k", linestyle="--", alpha=0.5)
    ax.set_xlabel("face - path (deg)  ≈ derived spin axis")
    ax.set_ylabel("count")
    ax.set_title(f"Face vs path consistency (n={len(diffs)})")
    ax.grid(alpha=0.3)

    fig.suptitle("Horizontal launch angle diagnostics", fontsize=14)
    fig.tight_layout()
    out = out_dir / "h_angle_overview.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"wrote {out}")


def plot_per_session(rows: list[ShotRow], out_dir: Path) -> None:
    sessions = sorted({r.session_id for r in rows})
    for sid in sessions:
        ses = [r for r in rows if r.session_id == sid]
        ses.sort(key=lambda r: r.shot_number)
        if not ses:
            continue

        fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)

        xs = [r.shot_number for r in ses]
        ax = axes[0]
        ax.plot(xs, [r.h_angle for r in ses], "o-",
                color=C_FACE, markersize=4, label="face (h_angle)", alpha=0.8)
        ax.plot(xs, [r.club_path_deg for r in ses], "s-",
                color=C_PATH, markersize=4, label="path", alpha=0.8)
        ax.axhline(0, color="k", linewidth=0.5)
        ax.axhline(15, color=C_DIFF, linestyle="--", alpha=0.4, label="±15° wall")
        ax.axhline(-15, color=C_DIFF, linestyle="--", alpha=0.4)
        ax.set_ylabel("angle (deg)")
        ax.set_title(f"{sid}  —  face/path per shot")
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(alpha=0.3)

        ax = axes[1]
        ball_speed = [r.ball_speed_mph or np.nan for r in ses]
        ax.plot(xs, ball_speed, "-", color="#2196F3", label="ball speed")
        ax2 = ax.twinx()
        snrs = [r.h_avg_snr_db if r.h_avg_snr_db is not None else np.nan
                for r in ses]
        ax2.plot(xs, snrs, "-", color="#4CAF50", alpha=0.7, label="h-radar avg SNR")
        ax.set_ylabel("ball speed (mph)", color="#2196F3")
        ax2.set_ylabel("avg SNR (dB)", color="#4CAF50")
        ax.grid(alpha=0.3)

        ax = axes[2]
        confs = [r.confidence if r.confidence is not None else 0 for r in ses]
        sources = [r.angle_source or "none" for r in ses]
        cmap = {"radar": "#4CAF50", "estimated": "#9E9E9E",
                "camera": "#2196F3", "none": "#F44336"}
        ax.bar(xs, confs, color=[cmap.get(s, "#F44336") for s in sources],
               edgecolor="k", linewidth=0.3)
        ax.set_ylabel("confidence")
        ax.set_xlabel("shot number")
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.3)
        # legend for source colors
        from matplotlib.patches import Patch
        ax.legend(handles=[Patch(color=v, label=k) for k, v in cmap.items()],
                  fontsize=7, loc="upper right")

        fig.tight_layout()
        out = out_dir / f"{sid}_h_angle.png"
        fig.savefig(out, dpi=120)
        plt.close(fig)
        print(f"wrote {out}")


def plot_face_vs_path_scatter(rows: list[ShotRow], out_dir: Path) -> None:
    pairs = [(r.h_angle, r.club_path_deg, r.confidence or 0)
             for r in rows
             if r.h_angle is not None and r.club_path_deg is not None]
    if not pairs:
        return
    xs = [p for _, p, _ in pairs]
    ys = [f for f, _, _ in pairs]
    cs = [c for _, _, c in pairs]
    fig, ax = plt.subplots(figsize=(8, 8))
    sc = ax.scatter(xs, ys, c=cs, cmap="viridis", s=30,
                    edgecolor="k", linewidth=0.3)
    lim = max(15, max(abs(min(xs + ys)), abs(max(xs + ys))))
    ax.plot([-lim, lim], [-lim, lim], "k--", alpha=0.5,
            label="face = path (zero spin axis)")
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_xlabel("club path (deg)")
    ax.set_ylabel("face / horizontal launch angle (deg)")
    ax.set_title(f"Face vs path scatter (n={len(pairs)})")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.colorbar(sc, ax=ax, label="confidence")
    out = out_dir / "face_vs_path_scatter.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"wrote {out}")


# ---------- CSV dump ----------


def write_csv(rows: list[ShotRow], out_dir: Path) -> None:
    out = out_dir / "h_angle_diag.csv"
    fields = [
        "session_id", "shot_number", "ts", "ball_speed_mph", "club_speed_mph",
        "angle_source", "h_angle", "v_angle", "confidence",
        "club_path_deg", "spin_axis_deg",
        "h_ball_angle", "h_confidence", "h_num_frames", "h_avg_snr_db",
        "h_buffer_frame_count", "h_buffer_span_s",
        "v_buffer_frame_count", "v_ball_angle", "v_confidence",
    ]
    with out.open("w") as fh:
        fh.write(",".join(fields) + "\n")
        for r in rows:
            fh.write(",".join(_csv(getattr(r, f)) for f in fields) + "\n")
    print(f"wrote {out}  ({len(rows)} rows)")


def _csv(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v).replace(",", ";")


# ---------- RADC capture mode (raw bytes — full FFT replay) ----------


def _import_radc():
    """Import openflight.kld7.radc lazily so JSONL mode doesn't pay the cost."""
    import sys

    project_root = Path(__file__).resolve().parents[2]
    src = project_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from openflight.kld7 import radc  # type: ignore

    return radc


def load_radc_capture(path: Path) -> dict:
    """Load a kld7_radc_*.pkl capture (output of capture_kld7_radc.py)."""
    import pickle

    with path.open("rb") as fh:
        return pickle.load(fh)


def group_frames_around_shots(
    capture: dict, ms_before: float = 1500.0, ms_after: float = 700.0,
) -> list[dict]:
    """For each OPS243 shot in the capture, gather K-LD7 frames around it.

    Mirrors the live tracker's get_angle_for_shot window so the offline
    replay sees the same frame set that the live pipeline would have.
    """
    shots = capture.get("ops243_shots") or []
    frames = capture.get("frames") or []
    out = []
    for s in shots:
        t = s.get("timestamp")
        if t is None:
            continue
        sel = [
            f for f in frames
            if f.get("radc") is not None
            and f.get("timestamp") is not None
            and (t - ms_before / 1000.0) <= f["timestamp"] <= (t + ms_after / 1000.0)
        ]
        out.append({
            "shot_timestamp": t,
            "ball_speed_mph": s.get("ball_speed_mph"),
            "club_speed_mph": s.get("club_speed_mph"),
            "frames": sel,
        })
    return out


def per_frame_breakdown(
    frames: list[dict],
    ball_speed_mph: Optional[float],
    fft_size: int = 2048,
    max_speed_kmh: float = 100.0,
) -> list[dict]:
    """For each frame in the impact window, compute the ball-band peak bin,
    per-bin angle at that peak, peak SNR, and the velocity that bin maps to.

    This is the diagnostic version of what extract_launch_angle does
    internally — but exposes the per-frame decisions instead of returning
    a single weighted answer.
    """
    radc = _import_radc()

    if ball_speed_mph is not None:
        b_lo, b_hi = radc.ball_bin_range_from_speed(
            ball_speed_mph, 10.0, fft_size, max_speed_kmh,
        )
    else:
        b_lo = radc._velocity_to_bin(-39.0, fft_size, max_speed_kmh)
        b_hi = radc._velocity_to_bin(-7.0, fft_size, max_speed_kmh)

    rows = []
    for fi, frame in enumerate(frames):
        rb = frame.get("radc")
        if rb is None:
            continue
        try:
            channels = radc.parse_radc_payload(rb)
        except ValueError:
            continue
        f1a_iq = radc.to_complex_iq(channels["f1a_i"], channels["f1a_q"])
        f2a_iq = radc.to_complex_iq(channels["f2a_i"], channels["f2a_q"])
        spec = radc.compute_spectrum(f1a_iq, fft_size=fft_size)
        ball_spec = spec[b_lo:b_hi]
        if ball_spec.size == 0 or ball_spec.max() <= 0:
            continue
        full_pos = spec[spec > 0]
        full_median = float(np.median(full_pos)) if full_pos.size else 0.0
        peak_val = float(ball_spec.max())
        snr = peak_val / full_median if full_median > 0 else 0.0

        peak_bin = b_lo + int(np.argmax(ball_spec))
        f1a_fft = radc.compute_fft_complex(f1a_iq, fft_size=fft_size)
        f2a_fft = radc.compute_fft_complex(f2a_iq, fft_size=fft_size)
        angles = radc.per_bin_angle_deg(f1a_fft, f2a_fft)
        peak_angle = float(angles[peak_bin])
        # The "next-best" bin (away from the peak) — useful to spot
        # ties / sidelobe contamination
        ball_angles = angles[b_lo:b_hi]

        rows.append({
            "frame_index": fi,
            "timestamp": frame.get("timestamp"),
            "peak_bin": peak_bin,
            "peak_velocity_kmh": radc.bin_to_velocity_kmh(
                peak_bin, fft_size, max_speed_kmh,
            ),
            "peak_snr": snr,
            "peak_angle_deg": peak_angle,
            "ball_band_lo": b_lo,
            "ball_band_hi": b_hi,
            "ball_band_max_db": 20.0 * np.log10(peak_val) if peak_val > 0 else 0.0,
            "ball_band_angles_min": float(ball_angles.min()),
            "ball_band_angles_max": float(ball_angles.max()),
            "ball_band_angle_p50": float(np.percentile(ball_angles, 50)),
        })
    return rows


def replay_capture(path: Path, out_dir: Path) -> None:
    radc = _import_radc()
    cap = load_radc_capture(path)
    md = cap.get("metadata", {})
    orientation = md.get("orientation", "?")
    print()
    print("=" * 100)
    print(f"RADC CAPTURE REPLAY  —  {path.name}")
    print(f"  orientation = {orientation}")
    print(f"  ops243 shots in capture = "
          f"{len(cap.get('ops243_shots') or [])}")
    print(f"  total frames = {md.get('total_frames')}  "
          f"(with RADC: {md.get('radc_frames')})")
    print("=" * 100)

    grouped = group_frames_around_shots(cap)
    if not grouped:
        print("No OPS243 shots found in capture; nothing to replay.")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []

    for shot_idx, g in enumerate(grouped, start=1):
        ball_mph = g["ball_speed_mph"]
        frames = g["frames"]
        if not frames:
            continue

        # Live pipeline result
        results = radc.extract_launch_angle(
            frames=frames,
            ops243_ball_speed_mph=ball_mph,
            speed_tolerance_mph=10.0,
            orientation=None,  # don't apply hard bounds — we want to see them
        )
        live = results[0] if results else None

        # Per-frame breakdown
        breakdown = per_frame_breakdown(frames, ball_mph)

        summary.append({
            "shot_idx": shot_idx,
            "ball_mph": ball_mph,
            "frames_in_window": len(frames),
            "frames_with_ball_detection": len(breakdown),
            "live_angle": live["launch_angle_deg"] if live else None,
            "live_confidence": live["confidence"] if live else None,
            "live_snr": live["avg_snr_db"] if live else None,
            "frame_count": live["frame_count"] if live else 0,
            "angle_std_deg": live["angle_std_deg"] if live else None,
            "per_frame_angles": [b["peak_angle_deg"] for b in breakdown],
            "per_frame_snr": [b["peak_snr"] for b in breakdown],
            "per_frame_bins": [b["peak_bin"] for b in breakdown],
        })

        # Plot per-shot diagnostic
        if breakdown:
            _plot_radc_shot(shot_idx, g, breakdown, live, out_dir)

    _print_radc_summary(summary, orientation)
    _plot_radc_overview(summary, orientation, out_dir)
    _write_radc_csv(summary, path, out_dir)


def _print_radc_summary(summary: list[dict], orientation: str) -> None:
    if not summary:
        print("\nno shots produced any frames; cannot summarize")
        return

    detected = [s for s in summary if s["live_angle"] is not None]
    print()
    print("Replay summary:")
    print(f"  shots replayed          : {len(summary)}")
    print(f"  shots with live angle   : {len(detected)}  "
          f"({len(detected)*100/len(summary):.1f}%)")

    if detected:
        angles = [s["live_angle"] for s in detected]
        confs = [s["live_confidence"] for s in detected]
        snrs = [s["live_snr"] for s in detected]
        print(f"  live angle              : "
              f"mean={np.mean(angles):+.2f}  std={np.std(angles):.2f}  "
              f"min={min(angles):+.1f}  max={max(angles):+.1f}")
        print(f"  live confidence         : "
              f"mean={np.mean(confs):.2f}  min={min(confs):.2f}")
        print(f"  live avg SNR (dB)       : "
              f"mean={np.mean(snrs):.1f}  min={min(snrs):.1f}")

    # Per-frame stability — are peaks bouncing across bins?
    per_shot_bin_jumps = []
    per_shot_angle_jumps = []
    for s in summary:
        bins = s["per_frame_bins"]
        angs = s["per_frame_angles"]
        if len(bins) >= 2:
            per_shot_bin_jumps.append(
                float(np.mean(np.abs(np.diff(bins))))
            )
            per_shot_angle_jumps.append(
                float(np.mean(np.abs(np.diff(angs))))
            )
    if per_shot_bin_jumps:
        print(f"  mean |Δ peak_bin| / shot   : "
              f"{np.mean(per_shot_bin_jumps):.1f} bins  "
              f"(small = stable peak; large = jumping target)")
        print(f"  mean |Δ peak_angle| / shot : "
              f"{np.mean(per_shot_angle_jumps):.1f}°  "
              f"(small = same target; large = noise-dominated)")


def _plot_radc_shot(
    shot_idx: int, group: dict, breakdown: list[dict],
    live_result: Optional[dict], out_dir: Path,
) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)

    fis = [b["frame_index"] for b in breakdown]
    bins = [b["peak_bin"] for b in breakdown]
    snrs = [b["peak_snr"] for b in breakdown]
    angs = [b["peak_angle_deg"] for b in breakdown]
    rng_lo = breakdown[0]["ball_band_lo"]
    rng_hi = breakdown[0]["ball_band_hi"]

    axes[0].plot(fis, bins, "o-", color="#2196F3")
    axes[0].axhline(rng_lo, color="k", linestyle="--", alpha=0.4,
                    label=f"ball band lo={rng_lo}")
    axes[0].axhline(rng_hi, color="k", linestyle="--", alpha=0.4,
                    label=f"ball band hi={rng_hi}")
    axes[0].set_ylabel("peak FFT bin")
    axes[0].set_title(
        f"shot {shot_idx}  —  ball_speed={group['ball_speed_mph']:.1f} mph"
        f"  —  {len(breakdown)} of {len(group['frames'])} frames detected"
    )
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)

    axes[1].plot(fis, snrs, "o-", color="#4CAF50")
    axes[1].axhline(2.0, color="k", linestyle="--", alpha=0.4,
                    label="multi-frame SNR floor (2.0)")
    axes[1].axhline(5.0, color="r", linestyle="--", alpha=0.4,
                    label="single-frame SNR floor (5.0)")
    axes[1].set_ylabel("peak SNR (linear)")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)

    axes[2].plot(fis, angs, "o-", color=C_FACE)
    if live_result is not None:
        axes[2].axhline(live_result["launch_angle_deg"], color=C_DIFF,
                        linestyle="--", alpha=0.8,
                        label=(f"live angle {live_result['launch_angle_deg']:+.1f}°  "
                               f"(conf {live_result['confidence']:.2f})"))
    axes[2].axhline(0, color="k", linewidth=0.5)
    axes[2].set_ylabel("peak-bin angle (deg)")
    axes[2].set_xlabel("frame index in window")
    axes[2].legend(fontsize=8)
    axes[2].grid(alpha=0.3)

    fig.tight_layout()
    out = out_dir / f"radc_shot_{shot_idx:02d}.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)


def _plot_radc_overview(
    summary: list[dict], orientation: str, out_dir: Path,
) -> None:
    if not summary:
        return
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    detected = [s for s in summary if s["live_angle"] is not None]
    if detected:
        axes[0].hist([s["live_angle"] for s in detected],
                     bins=np.arange(-20, 21, 1),
                     color=C_FACE, edgecolor="k", alpha=0.8)
        axes[0].axvline(0, color="k", linewidth=0.5)
        axes[0].set_xlabel(f"replayed live angle ({orientation}, deg)")
        axes[0].set_ylabel("count")
        axes[0].set_title("Replay angle distribution")
        axes[0].grid(alpha=0.3)

    # Frames detected vs frames in window — detection rate per shot
    in_win = [s["frames_in_window"] for s in summary]
    detected_frames = [s["frames_with_ball_detection"] for s in summary]
    rate = [
        d / max(1, w) for d, w in zip(detected_frames, in_win)
    ]
    axes[1].hist(rate, bins=20, color="#4CAF50", edgecolor="k", alpha=0.8)
    axes[1].set_xlabel("ball-detection rate per shot  (frames with peak ÷ frames in window)")
    axes[1].set_ylabel("count")
    axes[1].set_title("Per-shot detection rate")
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    out = out_dir / "radc_overview.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"wrote {out}")


def _write_radc_csv(summary: list[dict], src: Path, out_dir: Path) -> None:
    out = out_dir / "radc_replay.csv"
    fields = [
        "shot_idx", "ball_mph", "frames_in_window",
        "frames_with_ball_detection",
        "live_angle", "live_confidence", "live_snr", "frame_count",
        "angle_std_deg",
    ]
    with out.open("w") as fh:
        fh.write(f"# source: {src.name}\n")
        fh.write(",".join(fields) + "\n")
        for s in summary:
            fh.write(",".join(_csv(s.get(k)) for k in fields) + "\n")
    print(f"wrote {out}")


# ---------- main ----------


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("logs", nargs="*", type=Path,
                    help="JSONL session log paths (or globs expanded by shell)")
    ap.add_argument("--radc", type=Path, default=None,
                    help="Path to a kld7_radc_*.pkl raw RADC capture; "
                         "enables full FFT replay diagnostics")
    ap.add_argument("--output-dir", type=Path,
                    default=Path("session_logs/h_angle_diag"),
                    help="Where to write plots and CSV")
    args = ap.parse_args()

    if not args.logs and not args.radc:
        ap.error("provide at least one JSONL log path or --radc <pkl>")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.logs:
        paths = sorted({p.resolve() for p in args.logs if p.exists()})
        if paths:
            rows = load_sessions(paths)
            if rows:
                print_summary(rows)
                plot_distribution(rows, args.output_dir)
                plot_per_session(rows, args.output_dir)
                plot_face_vs_path_scatter(rows, args.output_dir)
                write_csv(rows, args.output_dir)
            else:
                print("warning: no shots in supplied JSONL logs")
        else:
            print("warning: no JSONL log paths matched")

    if args.radc:
        if not args.radc.exists():
            raise SystemExit(f"--radc path not found: {args.radc}")
        replay_capture(args.radc, args.output_dir)

    print()
    print(f"all artifacts in: {args.output_dir}")


if __name__ == "__main__":
    main()
