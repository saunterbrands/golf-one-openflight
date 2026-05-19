"""Tests for the temporary TrackMan-trained K-LD7 calibration experiment."""

from openflight import server as server_module
from openflight.kld7.trackman_calibration import (
    CALIBRATION_MODEL_NAME,
    calibrate_angle,
    calibrate_angle_with_metadata,
    training_samples,
)
from openflight.kld7.types import KLD7Angle
from openflight.launch_monitor import ClubType


def test_training_samples_replay_within_half_degree():
    """The two saved TrackMan sessions are the acceptance target for this experiment."""
    errors = []
    for sample in training_samples():
        calibrated = calibrate_angle(
            axis=sample.axis,
            raw_angle_deg=sample.raw_angle_deg,
            club=sample.club,
            ball_speed_mph=sample.ball_speed_mph,
            club_speed_mph=sample.club_speed_mph,
        )
        errors.append(abs(calibrated - sample.trackman_angle_deg))

    assert max(errors) <= 0.5


def test_calibration_accepts_club_type_enum():
    """Live server calls pass ClubType enums, while fixture samples store strings."""
    calibrated = calibrate_angle(
        axis="v",
        raw_angle_deg=17.1,
        club=ClubType.DRIVER,
        ball_speed_mph=154.571,
        club_speed_mph=104.473,
    )

    assert abs(calibrated - 8.844) <= 0.5


def test_calibration_metadata_identifies_exact_match():
    """Logs should show when a calibration came from a saved TrackMan pair."""
    result = calibrate_angle_with_metadata(
        axis="v",
        raw_angle_deg=17.1,
        club=ClubType.DRIVER,
        ball_speed_mph=154.571,
        club_speed_mph=104.473,
    )

    assert result.angle_deg == 8.8
    assert result.decision == "exact_match"
    assert result.nearest_session == "test2"
    assert result.nearest_shot_number == 59


def test_calibration_returns_raw_angle_when_outside_training_manifold():
    """The experimental fallback should avoid extrapolating far from samples."""
    result = calibrate_angle_with_metadata(
        axis="v",
        raw_angle_deg=40.0,
        club="driver",
        ball_speed_mph=10.0,
        club_speed_mph=5.0,
    )

    assert result.angle_deg == 40.0
    assert result.decision == "outside_training_manifold"


def test_fallback_knn_tuning_improves_leave_one_out_generalization():
    """Guard the v2 fallback against drifting back to the weaker v1 tuning."""
    samples = training_samples()
    errors = []
    within_half_degree = 0
    for index, sample in enumerate(samples):
        calibrated = calibrate_angle(
            axis=sample.axis,
            raw_angle_deg=sample.raw_angle_deg,
            club=sample.club,
            ball_speed_mph=sample.ball_speed_mph,
            club_speed_mph=sample.club_speed_mph,
            samples=samples[:index] + samples[index + 1 :],
        )
        error = abs(calibrated - sample.trackman_angle_deg)
        errors.append(error)
        within_half_degree += error <= 0.5

    assert sum(errors) / len(errors) < 3.75
    assert within_half_degree >= 28


def test_server_helper_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(server_module, "experimental_kld7_trackman_calibration", False)

    assert (
        server_module._apply_experimental_kld7_trackman_calibration(
            axis="v",
            angle_deg=17.1,
            club=ClubType.DRIVER,
            ball_speed_mph=154.571,
            club_speed_mph=104.473,
        )
        == 17.1
    )


def test_server_helper_applies_flagged_calibration(monkeypatch):
    monkeypatch.setattr(server_module, "experimental_kld7_trackman_calibration", True)

    calibrated = server_module._apply_experimental_kld7_trackman_calibration(
        axis="v",
        angle_deg=17.1,
        club=ClubType.DRIVER,
        ball_speed_mph=154.571,
        club_speed_mph=104.473,
    )

    assert abs(calibrated - 8.844) <= 0.5


def test_server_metadata_helper_reports_calibration_decision(monkeypatch):
    monkeypatch.setattr(server_module, "experimental_kld7_trackman_calibration", True)

    calibrated, details = server_module._calibrate_experimental_kld7_trackman_angle(
        axis="v",
        angle_deg=17.1,
        club=ClubType.DRIVER,
        ball_speed_mph=154.571,
        club_speed_mph=104.473,
    )

    assert abs(calibrated - 8.844) <= 0.5
    assert details is not None
    assert details["decision"] == "exact_match"
    assert details["nearest_session"] == "test2"
    assert details["nearest_shot_number"] == 59


def test_angle_log_payload_preserves_raw_and_calibrated_when_enabled(monkeypatch):
    monkeypatch.setattr(server_module, "experimental_kld7_trackman_calibration", True)

    angle = KLD7Angle(vertical_deg=8.8, confidence=0.7, num_frames=2)
    payload = server_module._kld7_angle_log_payload(
        angle,
        "vertical_deg",
        raw_angle_deg=17.1,
        calibration_details={
            "decision": "exact_match",
            "nearest_distance": 0.0,
            "nearest_session": "test2",
            "nearest_shot_number": 59,
            "nearest_axis": "v",
            "nearest_club": "driver",
            "model": CALIBRATION_MODEL_NAME,
        },
    )

    assert payload["vertical_deg"] == 8.8
    assert payload["raw_vertical_deg"] == 17.1
    assert payload["calibrated_vertical_deg"] == 8.8
    assert payload["calibration_model"] == CALIBRATION_MODEL_NAME
    assert payload["calibration_details"]["decision"] == "exact_match"
    assert payload["calibration_details"]["nearest_shot_number"] == 59
    assert payload["calibration_details"]["model"] == CALIBRATION_MODEL_NAME


def test_angle_log_payload_stays_compact_when_disabled(monkeypatch):
    monkeypatch.setattr(server_module, "experimental_kld7_trackman_calibration", False)

    angle = KLD7Angle(vertical_deg=8.8, confidence=0.7, num_frames=2)
    payload = server_module._kld7_angle_log_payload(
        angle,
        "vertical_deg",
        raw_angle_deg=17.1,
    )

    assert "raw_vertical_deg" not in payload
    assert "calibrated_vertical_deg" not in payload
    assert "calibration_model" not in payload
