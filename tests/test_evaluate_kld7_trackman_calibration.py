"""Tests for evaluating the flagged KLD7 TrackMan calibration."""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "analysis"))

import evaluate_kld7_trackman_calibration as eval_calibration


def _write_comparison(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "shot_number_of",
        "club",
        "ball_speed_of",
        "club_speed_of",
        "launch_v_of",
        "launch_v_tm",
        "launch_h_of",
        "launch_h_tm",
        "match_quality",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_load_pairs_reads_calibratable_good_angle_pairs(tmp_path):
    comparison = tmp_path / "comparison.csv"
    _write_comparison(
        comparison,
        [
            {
                "shot_number_of": 10,
                "club": "driver",
                "ball_speed_of": 150.0,
                "club_speed_of": 100.0,
                "launch_v_of": 12.0,
                "launch_v_tm": 10.0,
                "launch_h_of": "",
                "launch_h_tm": -2.0,
                "match_quality": "good",
            },
            {
                "shot_number_of": 11,
                "club": "driver",
                "ball_speed_of": 151.0,
                "club_speed_of": 101.0,
                "launch_v_of": 12.0,
                "launch_v_tm": 10.0,
                "launch_h_of": -1.0,
                "launch_h_tm": -2.0,
                "match_quality": "ball_speed_mismatch",
            },
        ],
    )

    pairs = eval_calibration.load_pairs([comparison])

    assert len(pairs) == 1
    assert pairs[0].source == "comparison.csv"
    assert pairs[0].shot_number == 10
    assert pairs[0].axis == "v"
    assert pairs[0].raw_angle_deg == 12.0


def test_load_pairs_can_filter_axis(tmp_path):
    comparison = tmp_path / "comparison.csv"
    _write_comparison(
        comparison,
        [
            {
                "shot_number_of": 10,
                "club": "driver",
                "ball_speed_of": 150.0,
                "club_speed_of": 100.0,
                "launch_v_of": 12.0,
                "launch_v_tm": 10.0,
                "launch_h_of": -1.0,
                "launch_h_tm": -2.0,
                "match_quality": "good",
            },
        ],
    )

    pairs = eval_calibration.load_pairs([comparison], axis="horizontal")

    assert [(pair.shot_number, pair.axis) for pair in pairs] == [(10, "h")]


def test_evaluate_pairs_applies_calibration(monkeypatch):
    pair = eval_calibration.CalibrationPair(
        source="comparison.csv",
        shot_number=10,
        axis="v",
        club="driver",
        ball_speed_mph=150.0,
        club_speed_mph=100.0,
        raw_angle_deg=12.0,
        trackman_angle_deg=10.0,
    )
    calls = []

    def fake_calibrate_angle(**kwargs):
        calls.append(kwargs)
        return 10.4

    monkeypatch.setattr(eval_calibration, "calibrate_angle", fake_calibrate_angle)

    rows = eval_calibration.evaluate_pairs([pair])

    assert rows[0].calibrated_angle_deg == 10.4
    assert rows[0].error_deg == 0.40000000000000036
    assert calls[0]["axis"] == "v"
    assert calls[0]["raw_angle_deg"] == 12.0
    assert calls[0]["club_speed_mph"] == 100.0


def test_leave_one_out_rows_remove_exact_target_from_training(monkeypatch):
    pairs = [
        eval_calibration.CalibrationPair(
            source="comparison.csv",
            shot_number=10,
            axis="v",
            club="driver",
            ball_speed_mph=150.0,
            club_speed_mph=100.0,
            raw_angle_deg=12.0,
            trackman_angle_deg=10.0,
        ),
        eval_calibration.CalibrationPair(
            source="comparison.csv",
            shot_number=11,
            axis="v",
            club="driver",
            ball_speed_mph=151.0,
            club_speed_mph=101.0,
            raw_angle_deg=13.0,
            trackman_angle_deg=11.0,
        ),
    ]
    training_sizes = []

    def fake_calibrate_angle(**kwargs):
        training_sizes.append(len(tuple(kwargs["samples"])))
        return 10.4

    monkeypatch.setattr(eval_calibration, "calibrate_angle", fake_calibrate_angle)

    rows = eval_calibration.leave_one_out_rows(pairs)

    assert [row.calibrated_angle_deg for row in rows] == [10.4, 10.4]
    assert training_sizes == [1, 1]


def test_source_holdout_rows_train_only_on_other_sources(monkeypatch):
    pairs = [
        eval_calibration.CalibrationPair(
            source="session-a.csv",
            shot_number=10,
            axis="v",
            club="driver",
            ball_speed_mph=150.0,
            club_speed_mph=100.0,
            raw_angle_deg=12.0,
            trackman_angle_deg=10.0,
        ),
        eval_calibration.CalibrationPair(
            source="session-b.csv",
            shot_number=11,
            axis="v",
            club="driver",
            ball_speed_mph=151.0,
            club_speed_mph=101.0,
            raw_angle_deg=13.0,
            trackman_angle_deg=11.0,
        ),
        eval_calibration.CalibrationPair(
            source="session-b.csv",
            shot_number=12,
            axis="h",
            club="driver",
            ball_speed_mph=151.0,
            club_speed_mph=101.0,
            raw_angle_deg=-3.0,
            trackman_angle_deg=-4.0,
        ),
    ]
    training_sources_by_call = []

    def fake_calibrate_angle(**kwargs):
        training_sources_by_call.append(sorted({sample.session for sample in kwargs["samples"]}))
        return 10.4

    monkeypatch.setattr(eval_calibration, "calibrate_angle", fake_calibrate_angle)

    rows_by_source = eval_calibration.source_holdout_rows(pairs)

    assert sorted(rows_by_source) == ["session-a.csv", "session-b.csv"]
    assert [row.shot_number for row in rows_by_source["session-a.csv"]] == [10]
    assert [row.shot_number for row in rows_by_source["session-b.csv"]] == [11, 12]
    assert training_sources_by_call == [
        ["session-b.csv"],
        ["session-a.csv"],
        ["session-a.csv"],
    ]


def test_summary_and_gate_require_every_pair_within_limit():
    rows = [
        eval_calibration.CalibrationRow(
            source="a.csv",
            shot_number=1,
            axis="v",
            club="driver",
            ball_speed_mph=150.0,
            club_speed_mph=100.0,
            raw_angle_deg=12.0,
            trackman_angle_deg=10.0,
            calibrated_angle_deg=10.4,
            error_deg=0.4,
        ),
        eval_calibration.CalibrationRow(
            source="a.csv",
            shot_number=2,
            axis="h",
            club="driver",
            ball_speed_mph=150.0,
            club_speed_mph=100.0,
            raw_angle_deg=-1.0,
            trackman_angle_deg=-2.0,
            calibrated_angle_deg=-2.6,
            error_deg=-0.6,
        ),
    ]

    summary = eval_calibration.summarize(rows, max_error_deg=0.5)

    assert summary.attempted == 2
    assert summary.within_limit == 1
    assert summary.max_abs_error == 0.6
    assert summary.axis_counts == {"h": 1, "v": 1}
    assert not eval_calibration.passes_gate(summary, max_error_deg=0.5)


def test_source_holdout_gate_requires_every_source_to_pass():
    passing = eval_calibration.CalibrationSummary(
        attempted=1,
        within_limit=1,
        max_abs_error=0.4,
        mae=0.4,
        p90_abs_error=0.4,
        axis_counts={"v": 1},
        source_counts={"a.csv": 1},
    )
    failing = eval_calibration.CalibrationSummary(
        attempted=1,
        within_limit=0,
        max_abs_error=0.6,
        mae=0.6,
        p90_abs_error=0.6,
        axis_counts={"v": 1},
        source_counts={"b.csv": 1},
    )

    assert eval_calibration.passes_all_source_holdouts(
        {"a.csv": passing},
        max_error_deg=0.5,
    )
    assert not eval_calibration.passes_all_source_holdouts(
        {"a.csv": passing, "b.csv": failing},
        max_error_deg=0.5,
    )
    assert not eval_calibration.passes_all_source_holdouts({}, max_error_deg=0.5)


def test_source_holdout_baselines_include_raw_and_axis_club_mean():
    pairs = [
        eval_calibration.CalibrationPair(
            source="a.csv",
            shot_number=1,
            axis="v",
            club="driver",
            ball_speed_mph=150.0,
            club_speed_mph=100.0,
            raw_angle_deg=5.0,
            trackman_angle_deg=10.0,
        ),
        eval_calibration.CalibrationPair(
            source="b.csv",
            shot_number=2,
            axis="v",
            club="driver",
            ball_speed_mph=151.0,
            club_speed_mph=101.0,
            raw_angle_deg=11.0,
            trackman_angle_deg=12.0,
        ),
        eval_calibration.CalibrationPair(
            source="b.csv",
            shot_number=3,
            axis="v",
            club="driver",
            ball_speed_mph=152.0,
            club_speed_mph=102.0,
            raw_angle_deg=13.0,
            trackman_angle_deg=14.0,
        ),
        eval_calibration.CalibrationPair(
            source="b.csv",
            shot_number=4,
            axis="v",
            club="driver",
            ball_speed_mph=153.0,
            club_speed_mph=103.0,
            raw_angle_deg=15.0,
            trackman_angle_deg=16.0,
        ),
    ]

    baselines = eval_calibration.summarize_source_holdout_baselines(
        pairs,
        max_error_deg=0.5,
    )

    assert baselines["raw_angle"]["a.csv"].mae == 5.0
    assert baselines["axis_club_trackman_mean"]["a.csv"].mae == 4.0
    assert baselines["axis_club_trackman_mean"]["a.csv"].max_abs_error == 4.0


def test_summarize_by_axis_splits_vertical_and_horizontal_rows():
    rows = [
        eval_calibration.CalibrationRow(
            source="a.csv",
            shot_number=1,
            axis="v",
            club="driver",
            ball_speed_mph=150.0,
            club_speed_mph=100.0,
            raw_angle_deg=12.0,
            trackman_angle_deg=10.0,
            calibrated_angle_deg=10.4,
            error_deg=0.4,
        ),
        eval_calibration.CalibrationRow(
            source="a.csv",
            shot_number=2,
            axis="h",
            club="driver",
            ball_speed_mph=150.0,
            club_speed_mph=100.0,
            raw_angle_deg=-1.0,
            trackman_angle_deg=-2.0,
            calibrated_angle_deg=-2.6,
            error_deg=-0.6,
        ),
    ]

    by_axis = eval_calibration.summarize_by_axis(rows, max_error_deg=0.5)

    assert by_axis["v"].attempted == 1
    assert by_axis["v"].within_limit == 1
    assert by_axis["h"].attempted == 1
    assert by_axis["h"].within_limit == 0


def test_write_outputs_include_gate_result(tmp_path):
    row = eval_calibration.CalibrationRow(
        source="a.csv",
        shot_number=1,
        axis="v",
        club="driver",
        ball_speed_mph=150.0,
        club_speed_mph=100.0,
        raw_angle_deg=12.0,
        trackman_angle_deg=10.0,
        calibrated_angle_deg=10.4,
        error_deg=0.4,
    )
    rows_output = tmp_path / "rows.csv"
    summary_output = tmp_path / "summary.json"
    summary = eval_calibration.summarize([row], max_error_deg=0.5)

    eval_calibration.write_rows(rows_output, [row])
    leave_one_out_summary = eval_calibration.summarize(
        [
            eval_calibration.CalibrationRow(
                source="a.csv",
                shot_number=2,
                axis="v",
                club="driver",
                ball_speed_mph=150.0,
                club_speed_mph=100.0,
                raw_angle_deg=12.0,
                trackman_angle_deg=10.0,
                calibrated_angle_deg=12.0,
                error_deg=2.0,
            )
        ],
        max_error_deg=0.5,
    )
    eval_calibration.write_summary(
        summary_output,
        summary,
        axis="vertical",
        max_error_deg=0.5,
        leave_one_out_summary=leave_one_out_summary,
        by_axis={"v": summary},
        leave_one_out_by_axis={"v": leave_one_out_summary},
        source_holdout={"a.csv": leave_one_out_summary},
        source_holdout_baselines={"raw_angle": {"a.csv": leave_one_out_summary}},
    )

    written_rows = list(csv.DictReader(rows_output.open(encoding="utf-8")))
    assert written_rows[0]["calibrated_angle_deg"] == "10.4"
    payload = json.loads(summary_output.read_text(encoding="utf-8"))
    assert payload["passes_gate"] is True
    assert payload["leave_one_out"]["passes_gate"] is False
    assert payload["leave_one_out"]["max_abs_error"] == 2.0
    assert payload["by_axis"]["v"]["passes_gate"] is True
    assert payload["leave_one_out_by_axis"]["v"]["passes_gate"] is False
    assert payload["source_holdout"]["a.csv"]["passes_gate"] is False
    assert payload["source_holdout_baselines"]["raw_angle"]["a.csv"]["passes_gate"] is False
    assert payload["source_counts"] == {"a.csv": 1}


def test_cli_returns_pass_and_fail(tmp_path, monkeypatch, capsys):
    comparison = tmp_path / "comparison.csv"
    _write_comparison(
        comparison,
        [
            {
                "shot_number_of": 10,
                "club": "driver",
                "ball_speed_of": 150.0,
                "club_speed_of": 100.0,
                "launch_v_of": 12.0,
                "launch_v_tm": 10.0,
                "launch_h_of": "",
                "launch_h_tm": "",
                "match_quality": "good",
            },
        ],
    )

    monkeypatch.setattr(eval_calibration, "calibrate_angle", lambda **kwargs: 10.4)
    args = ["--comparison", str(comparison), "--require-within-limit"]

    assert eval_calibration.main(args) == 0
    captured = capsys.readouterr()
    assert "PASS: calibration satisfies" in captured.out
    assert "leave_one_out_attempted" in captured.out
    assert "leave_one_out_by_axis" in captured.out
    assert "source_holdout" in captured.out
    assert "source_holdout_baseline" in captured.out

    monkeypatch.setattr(eval_calibration, "calibrate_angle", lambda **kwargs: 10.6)

    assert eval_calibration.main(args) == 2
    assert "FAIL: calibration does not satisfy" in capsys.readouterr().err


def test_cli_can_require_source_holdout(tmp_path, monkeypatch, capsys):
    comparison_a = tmp_path / "comparison-a.csv"
    comparison_b = tmp_path / "comparison-b.csv"
    _write_comparison(
        comparison_a,
        [
            {
                "shot_number_of": 10,
                "club": "driver",
                "ball_speed_of": 150.0,
                "club_speed_of": 100.0,
                "launch_v_of": 12.0,
                "launch_v_tm": 10.0,
                "launch_h_of": "",
                "launch_h_tm": "",
                "match_quality": "good",
            },
        ],
    )
    _write_comparison(
        comparison_b,
        [
            {
                "shot_number_of": 11,
                "club": "driver",
                "ball_speed_of": 151.0,
                "club_speed_of": 101.0,
                "launch_v_of": 13.0,
                "launch_v_tm": 11.0,
                "launch_h_of": "",
                "launch_h_tm": "",
                "match_quality": "good",
            },
        ],
    )

    monkeypatch.setattr(eval_calibration, "calibrate_angle", lambda **kwargs: 10.4)

    assert (
        eval_calibration.main(
            [
                "--comparison",
                str(comparison_a),
                "--comparison",
                str(comparison_b),
                "--require-source-holdout",
            ]
        )
        == 2
    )
    assert "source-holdout" in capsys.readouterr().err

    monkeypatch.setattr(
        eval_calibration,
        "source_holdout_rows",
        lambda pairs: {"comparison-a.csv": eval_calibration.evaluate_pairs(pairs[:1])},
    )

    assert (
        eval_calibration.main(
            [
                "--comparison",
                str(comparison_a),
                "--comparison",
                str(comparison_b),
                "--require-source-holdout",
            ]
        )
        == 0
    )
    assert "PASS: calibration satisfies the source-holdout" in capsys.readouterr().out
