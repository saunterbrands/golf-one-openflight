#!/usr/bin/env python3
"""
Show raw frame data around swings accepted by the new filter code.
For each accepted detection, prints the TDAT/PDAT readings in the
shot window so you can see exactly what the radar saw.

Usage:
    python scripts/show_accepted_swings.py session_logs/kld7_capture_*.pkl
"""
import pickle
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openflight.kld7.tracker import KLD7Tracker
from openflight.kld7.types import KLD7Frame
from openflight.launch_monitor import ClubType


CLUB_MAP = {
    "driver": ClubType.DRIVER,
    "3wood": ClubType.WOOD_3, "3w": ClubType.WOOD_3,
    "5wood": ClubType.WOOD_5, "5w": ClubType.WOOD_5,
    "3i": ClubType.IRON_3, "4i": ClubType.IRON_4,
    "5i": ClubType.IRON_5, "6i": ClubType.IRON_6,
    "7i": ClubType.IRON_7, "8i": ClubType.IRON_8, "9i": ClubType.IRON_9,
    "pw": ClubType.PW, "gw": ClubType.GW,
    "sw": ClubType.SW, "lw": ClubType.LW,
    "wedge": ClubType.SW,
}


def club_from_filename(path):
    stem = path.stem.lower()
    for key, club in CLUB_MAP.items():
        if key in stem:
            return club
    return ClubType.UNKNOWN


def find_swings(frames, min_speed_kmh=15.0, club_min_m=0.8, club_max_m=2.5, gap_s=2.0):
    bursts = []
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
                current_burst = [t, t]
                bursts.append(current_burst)
            else:
                current_burst[1] = t
            last_detection_t = t
        else:
            if last_detection_t and t - last_detection_t > gap_s:
                current_burst = None

    return [b[1] for b in bursts]


def show_frames_in_window(frames_raw, swing_ts, shot_ts, window_pre=0.3, window_post=0.4):
    """Print every frame in a window around the shot, highlighting ball-range targets."""
    t_start = shot_ts - window_pre
    t_end = shot_ts + window_post

    print(f"  {'rel_ms':>8}  {'src':>4}  {'dist(m)':>8}  {'speed':>7}  {'angle':>7}  {'mag':>6}  note")
    print(f"  {'--------':>8}  {'----':>4}  {'--------':>8}  {'-------':>7}  {'-------':>7}  {'------':>6}  ----")

    for f in frames_raw:
        t = f.get("timestamp", 0)
        if not (t_start <= t <= t_end):
            continue

        rel_ms = (t - shot_ts) * 1000
        marker = "  <<SHOT>>" if abs(rel_ms) < 5 else ""

        tdat = f.get("tdat")
        pdat = [p for p in f.get("pdat", []) if p is not None]

        if not tdat and not pdat:
            print(f"  {rel_ms:>8.1f}  {'---':>4}  (no detections)")
            continue

        if tdat:
            d = tdat["distance"]
            ball_range = 3.8 <= d <= 5.5
            note = "BALL RANGE" if ball_range else ""
            print(f"  {rel_ms:>8.1f}  TDAT  {d:>8.2f}  {tdat['speed']:>7.1f}  {tdat['angle']:>6.1f}d  {tdat['magnitude']:>6.0f}  {note}{marker}")

        for pt in pdat:
            d = pt["distance"]
            ball_range = 3.8 <= d <= 5.5
            note = "BALL RANGE" if ball_range else ""
            print(f"  {rel_ms:>8.1f}  PDAT  {d:>8.2f}  {pt['speed']:>7.1f}  {pt['angle']:>6.1f}d  {pt['magnitude']:>6.0f}  {note}")


def main():
    for pkl in sys.argv[1:]:
        path = Path(pkl)
        with open(path, "rb") as f:
            data = pickle.load(f)

        frames_raw = data["frames"]
        club = club_from_filename(path)
        gate = KLD7Tracker.CLUB_ANGLE_GATES.get(club, (0.0, KLD7Tracker.BALL_MAX_LAUNCH_ANGLE_DEG))

        print(f"\n{'='*70}")
        print(f"  {path.name}")
        print(f"  club={club.value}  gate={gate[0]:.0f}-{gate[1]:.0f}deg")
        print(f"{'='*70}")

        swing_times = find_swings(frames_raw)
        frames = [
            KLD7Frame(timestamp=f.get("timestamp", 0), tdat=f.get("tdat"), pdat=f.get("pdat", []))
            for f in frames_raw
        ]

        tracker = KLD7Tracker()

        for i, swing_ts in enumerate(swing_times):
            shot_ts = swing_ts + 0.05

            # Load ring buffer
            tracker._ring_buffer = deque(maxlen=68)
            for frame in frames:
                if swing_ts - 2.0 <= frame.timestamp <= swing_ts + 0.5:
                    tracker._ring_buffer.append(frame)

            result = tracker.get_angle_for_shot(shot_timestamp=shot_ts, club=club)

            status = f"ACCEPTED  angle={result.vertical_deg:.1f}deg  conf={result.confidence:.2f}  dist={result.distance_m:.2f}m  frames={result.num_frames}" if result else "rejected"
            print(f"\n  Swing {i+1}  (swing_t={swing_ts:.3f})  [{status}]")

            if result:
                print(f"  Frames in window (shot_t={shot_ts:.3f}, -{tracker.BALL_SHOT_WINDOW_PRE_S*1000:.0f}ms/+{tracker.BALL_SHOT_WINDOW_POST_S*1000:.0f}ms):")
                show_frames_in_window(frames_raw, swing_ts, shot_ts,
                                      window_pre=tracker.BALL_SHOT_WINDOW_PRE_S + 0.05,
                                      window_post=tracker.BALL_SHOT_WINDOW_POST_S + 0.05)

    print()


if __name__ == "__main__":
    main()
