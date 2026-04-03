#!/usr/bin/env python3
"""Print swing timestamps with inter-swing gaps to identify duplicates."""
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def find_swings(frames, min_speed_kmh=15.0, club_min_m=0.8, club_max_m=2.5, gap_s=2.0):
    swing_times = []
    in_swing = False
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
            if not in_swing or (last_detection_t and t - last_detection_t > gap_s):
                swing_times.append(t)
                in_swing = True
            last_detection_t = t
        else:
            if last_detection_t and t - last_detection_t > gap_s:
                in_swing = False

    return swing_times


for pkl in sys.argv[1:]:
    with open(pkl, "rb") as f:
        data = pickle.load(f)

    frames = data["frames"]
    swings = find_swings(frames)
    t0 = swings[0] if swings else 0

    print(f"\n{Path(pkl).name}  ({len(frames)} frames, {len(swings)} swing triggers)")
    print(f"  {'#':>3}  {'abs_t(s)':>12}  {'rel_t(s)':>9}  {'gap_from_prev':>15}  note")
    print(f"  {'---':>3}  {'------------':>12}  {'---------':>9}  {'---------------':>15}  ----")

    for i, ts in enumerate(swings):
        rel = ts - t0
        if i == 0:
            gap_str = "---"
            note = "first"
        else:
            gap = ts - swings[i - 1]
            gap_str = f"+{gap:.3f}s"
            if gap < 1.5:
                note = "** likely same swing **"
            elif gap < 4.0:
                note = "? possible same swing"
            else:
                note = ""
        print(f"  {i+1:>3}  {ts:>12.3f}  {rel:>9.3f}  {gap_str:>15}  {note}")
