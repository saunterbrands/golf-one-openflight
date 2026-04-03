#!/usr/bin/env python3
"""
Compare old (no filters) vs new (all filters) K-LD7 ball extraction
against all pkl capture files.

Old code: no shot window, no precursor, no angle gate
New code: shot window +/-50ms/+200ms, precursor required, angle 0-40deg

Usage:
    python scripts/compare_kld7_filters.py session_logs/kld7_capture_*.pkl
"""
import argparse
import pickle
import sys
from collections import deque
from pathlib import Path

# Ensure project src is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openflight.kld7.tracker import KLD7Tracker
from openflight.kld7.types import KLD7Frame
from openflight.launch_monitor import ClubType


def club_from_filename(path: Path):
    """Infer ClubType from capture filename (e.g. '...-wedge.pkl', '...-7i.pkl')."""
    stem = path.stem.lower()
    mapping = {
        "driver": ClubType.DRIVER,
        "3wood": ClubType.WOOD_3, "3w": ClubType.WOOD_3,
        "5wood": ClubType.WOOD_5, "5w": ClubType.WOOD_5,
        "3i": ClubType.IRON_3, "4i": ClubType.IRON_4,
        "5i": ClubType.IRON_5, "6i": ClubType.IRON_6,
        "7i": ClubType.IRON_7, "8i": ClubType.IRON_8, "9i": ClubType.IRON_9,
        "pw": ClubType.PW, "gw": ClubType.GW,
        "sw": ClubType.SW, "lw": ClubType.LW,
        "wedge": ClubType.SW,  # generic "wedge" → sand wedge as representative mid-wedge
    }
    for key, club in mapping.items():
        if key in stem:
            return club
    return ClubType.UNKNOWN


def load_capture(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def find_swings(frames, min_speed_kmh=15.0, club_min_m=0.8, club_max_m=2.5, gap_s=2.0):
    """
    Find swing timestamps: last detection frame of each close-range high-speed burst.
    Using the last frame (not first) because it's closest to actual impact — the first
    trigger may be pre-swing setup activity up to ~1s before contact.
    """
    bursts = []          # list of [t0, t_last] for each burst
    current_burst = None
    last_detection_t = None

    for f in frames:
        t = f.get("timestamp", 0)
        found = False

        tdat = f.get("tdat")
        if tdat and club_min_m <= tdat.get("distance", 0) <= club_max_m and abs(tdat.get("speed", 0)) >= min_speed_kmh:
            found = True

        if not found:
            for pt in f.get("pdat", []):
                if pt and club_min_m <= pt.get("distance", 0) <= club_max_m and abs(pt.get("speed", 0)) >= min_speed_kmh:
                    found = True
                    break

        if found:
            if current_burst is None or (last_detection_t and t - last_detection_t > gap_s):
                # New burst
                current_burst = [t, t]
                bursts.append(current_burst)
            else:
                current_burst[1] = t  # extend end of current burst
            last_detection_t = t
        else:
            if last_detection_t and t - last_detection_t > gap_s:
                current_burst = None

    # Return the last timestamp of each burst (closest to impact)
    return [b[1] for b in bursts]


def run_extraction(frames_raw, swing_times, use_filters, club=None):
    """
    For each swing, load a 2s ring buffer ending at swing_ts+0.5s and
    call get_angle_for_shot with or without filters.

    use_filters=False simulates old code: no shot window, no precursor, no angle gate.
    use_filters=True uses current code including dynamic per-club angle gates.
    """
    tracker = KLD7Tracker()
    results = []

    if not use_filters:
        tracker.BALL_SHOT_WINDOW_PRE_S = 999.0
        tracker.BALL_SHOT_WINDOW_POST_S = 999.0
        tracker.BALL_MAX_LAUNCH_ANGLE_DEG = 999.0
        tracker.CLUB_ANGLE_GATES = {}  # disable per-club gates
        tracker._has_swing_precursor = lambda ts: True

    # Convert raw dicts to KLD7Frame objects
    frames = [
        KLD7Frame(
            timestamp=f.get("timestamp", 0),
            tdat=f.get("tdat"),
            pdat=f.get("pdat", []),
        )
        for f in frames_raw
    ]

    for swing_ts in swing_times:
        window_start = swing_ts - 2.0
        window_end = swing_ts + 0.5
        tracker._ring_buffer = deque(maxlen=68)
        for frame in frames:
            if window_start <= frame.timestamp <= window_end:
                tracker._ring_buffer.append(frame)

        shot_ts = swing_ts + 0.05

        passed_club = club if use_filters else None
        angle = tracker.get_angle_for_shot(shot_timestamp=shot_ts, club=passed_club)
        results.append((swing_ts, angle))

    return results


def summarize(label, results):
    detections = [(ts, a) for ts, a in results if a is not None]
    total = len(results)
    det = len(detections)
    print(f"  [{label}] {det}/{total} detections ({100*det//total if total else 0}%)")
    for ts, a in detections:
        print(f"    t={ts:.3f}s  angle={a.vertical_deg:.1f}deg  conf={a.confidence:.2f}  dist={a.distance_m:.2f}m  frames={a.num_frames}")


def compare(path):
    path = Path(path)
    data = load_capture(path)
    frames = data["frames"]
    club = club_from_filename(path)
    gate = KLD7Tracker.CLUB_ANGLE_GATES.get(club, (0.0, KLD7Tracker.BALL_MAX_LAUNCH_ANGLE_DEG))

    print(f"\n{'='*60}")
    print(f"  {path.name}")
    print(f"  {len(frames)} frames  |  club={club.value}  gate={gate[0]:.0f}-{gate[1]:.0f}deg")
    print(f"{'='*60}")

    swing_times = find_swings(frames)
    print(f"  Swings detected: {len(swing_times)}")

    old_results = run_extraction(frames, swing_times, use_filters=False, club=None)
    new_results = run_extraction(frames, swing_times, use_filters=True, club=club)

    print()
    summarize("OLD - no filters", old_results)
    print()
    summarize("NEW - with filters + club gate", new_results)

    # Side-by-side per swing
    print()
    print(f"  {'swing#':>7}  {'swing_t':>8}  {'OLD angle':>10}  {'OLD conf':>9}  {'NEW angle':>10}  {'NEW conf':>9}  verdict")
    print(f"  {'-------':>7}  {'--------':>8}  {'----------':>10}  {'---------':>9}  {'----------':>10}  {'---------':>9}  -------")
    for i, ((ts, old_a), (_, new_a)) in enumerate(zip(old_results, new_results)):
        old_str = f"{old_a.vertical_deg:6.1f}deg" if old_a else "  ---   "
        old_conf = f"{old_a.confidence:.2f}" if old_a else " ---"
        new_str = f"{new_a.vertical_deg:6.1f}deg" if new_a else "  ---   "
        new_conf = f"{new_a.confidence:.2f}" if new_a else " ---"

        if old_a and new_a:
            verdict = "both"
        elif old_a and not new_a:
            verdict = "old only (filtered out)"
        elif not old_a and new_a:
            verdict = "new only"
        else:
            verdict = "neither"

        print(f"  {i+1:>7}  {ts:8.3f}  {old_str:>10}  {old_conf:>9}  {new_str:>10}  {new_conf:>9}  {verdict}")


def main():
    parser = argparse.ArgumentParser(description="Compare old vs new K-LD7 filter performance")
    parser.add_argument("files", nargs="+", help="Path(s) to .pkl capture files")
    args = parser.parse_args()

    for f in args.files:
        compare(f)

    print()


if __name__ == "__main__":
    main()
