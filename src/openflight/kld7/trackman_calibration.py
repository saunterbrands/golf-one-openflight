"""Experimental TrackMan-trained correction for K-LD7 launch angles.

This module is intentionally not part of the default signal path. The JSONL
logs from the two TrackMan comparison sessions preserved K-LD7 output angles,
ball speed, club speed, and club, but not raw RADC bytes. That means those
sessions can train an empirical correction layer, but cannot validate a new
FFT/phase extraction choice end-to-end.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


@dataclass(frozen=True)
class TrackmanCalibrationSample:
    axis: str
    club: str
    ball_speed_mph: float
    club_speed_mph: float
    raw_angle_deg: float
    trackman_angle_deg: float
    session: str
    shot_number: int


@dataclass(frozen=True)
class TrackmanCalibrationResult:
    """Angle plus diagnostics for the experimental calibration decision."""

    angle_deg: float
    raw_angle_deg: float
    decision: str
    nearest_distance: float | None
    nearest_session: str | None
    nearest_shot_number: int | None
    nearest_axis: str | None
    nearest_club: str | None


CALIBRATION_MODEL_NAME = "experimental_trackman_knn_v2"


_RAW_SAMPLES: tuple[tuple[str, str, float, float, float, float, str, int], ...] = (
    ("v", "driver", 149.174, 100.604, 1.7, 8.061, "20260506", 10),
    ("v", "driver", 148.665, 101.316, 10.6, 14.449, "20260506", 11),
    ("v", "driver", 158.033, 106.611, 12.0, 10.269, "20260506", 12),
    ("v", "driver", 159.662, 107.833, 10.2, 12.331, "20260506", 14),
    ("h", "driver", 159.662, 107.833, -1.3, -4.293, "20260506", 14),
    ("v", "driver", 151.516, 104.982, 10.8, 12.304, "20260506", 15),
    ("h", "driver", 151.516, 104.982, -6.8, -7.526, "20260506", 15),
    ("v", "driver", 155.08, 105.491, 9.3, 7.71, "20260506", 16),
    ("v", "driver", 155.08, 104.371, 7.7, 10.249, "20260506", 17),
    ("v", "7-iron", 120.969, 81.257, 11.7, 15.353, "20260506", 1),
    ("h", "7-iron", 120.969, 81.257, 3.0, -1.226, "20260506", 1),
    ("v", "7-iron", 108.852, 79.22, 5.2, 15.47, "20260506", 2),
    ("h", "7-iron", 108.852, 79.22, 8.9, -0.277, "20260506", 2),
    ("v", "7-iron", 116.081, 79.526, 25.3, 16.652, "20260506", 3),
    ("h", "7-iron", 116.081, 79.526, -6.4, 0.661, "20260506", 3),
    ("v", "7-iron", 116.896, 80.442, 4.8, 18.237, "20260506", 4),
    ("h", "7-iron", 116.896, 80.442, -6.2, 1.529, "20260506", 4),
    ("v", "7-iron", 115.368, 80.646, 13.0, 16.592, "20260506", 5),
    ("h", "7-iron", 115.368, 80.646, -7.4, 0.131, "20260506", 5),
    ("v", "7-iron", 117.201, 79.526, 8.9, 16.741, "20260506", 6),
    ("h", "7-iron", 117.201, 79.526, -7.3, 0.263, "20260506", 6),
    ("v", "7-iron", 119.136, 80.035, 8.4, 17.034, "20260506", 7),
    ("h", "7-iron", 119.136, 80.035, -13.8, 0.71, "20260506", 7),
    ("v", "7-iron", 122.292, 82.071, 1.8, 14.211, "20260506", 8),
    ("h", "7-iron", 122.292, 82.071, 4.0, -3.528, "20260506", 8),
    ("v", "pw", 98.669, 69.038, 14.8, 21.545, "20260506", 18),
    ("h", "pw", 98.669, 69.038, 4.1, -1.509, "20260506", 18),
    ("v", "pw", 102.131, 69.547, 23.0, 21.941, "20260506", 19),
    ("v", "pw", 99.484, 68.834, 5.6, 23.166, "20260506", 20),
    ("h", "pw", 99.484, 68.834, 1.3, -0.97, "20260506", 20),
    ("v", "pw", 80.951, 67.612, 11.2, 18.543, "20260506", 21),
    ("v", "pw", 98.669, 78.609, 23.1, 19.892, "20260506", 22),
    ("h", "pw", 98.669, 78.609, 0.0, -5.616, "20260506", 22),
    ("v", "pw", 101.927, 76.98, 2.4, 21.923, "20260506", 23),
    ("v", "pw", 98.262, 77.489, 12.4, 21.199, "20260506", 24),
    ("v", "driver", 154.571, 104.473, 17.1, 8.844, "test2", 59),
    ("h", "driver", 154.571, 104.473, -7.3, -9.757, "test2", 59),
    ("v", "driver", 151.109, 104.371, 11.1, 9.761, "test2", 60),
    ("h", "driver", 151.109, 104.371, -7.5, -9.007, "test2", 60),
    ("v", "driver", 153.044, 104.677, 13.5, 13.829, "test2", 61),
    ("h", "driver", 153.044, 104.677, 2.7, -5.329, "test2", 61),
    ("v", "driver", 152.433, 105.084, 3.0, 13.907, "test2", 62),
    ("h", "driver", 152.433, 105.084, 8.9, -5.367, "test2", 62),
    ("v", "driver", 149.073, 101.316, 12.4, 16.755, "test2", 63),
    ("h", "driver", 149.073, 101.316, -5.1, -4.075, "test2", 63),
    ("v", "driver", 131.355, 92.763, 13.4, 9.006, "test2", 64),
    ("h", "driver", 131.355, 92.763, -1.1, -8.979, "test2", 64),
    ("v", "driver", 125.856, 90.319, 10.8, 15.859, "test2", 65),
    ("h", "driver", 125.856, 90.319, -8.3, 0.826, "test2", 65),
    ("v", "driver", 118.423, 86.959, 10.9, 16.04, "test2", 66),
    ("h", "driver", 118.423, 86.959, -6.8, -6.975, "test2", 66),
    ("v", "driver", 121.274, 93.069, 12.2, 6.699, "test2", 67),
    ("h", "driver", 121.274, 93.069, 0.8, -13.885, "test2", 67),
    ("v", "driver", 127.791, 89.708, 11.3, 16.177, "test2", 68),
    ("h", "driver", 127.791, 89.708, -10.7, -2.029, "test2", 68),
    ("v", "driver", 135.937, 93.578, 11.3, 10.455, "test2", 69),
    ("h", "driver", 135.937, 93.578, -13.9, -8.581, "test2", 69),
    ("v", "3-wood", 141.334, 97.956, 21.4, 11.875, "test2", 49),
    ("h", "3-wood", 141.334, 97.956, -3.1, -4.932, "test2", 49),
    ("v", "3-wood", 134.206, 92.967, 16.8, 15.042, "test2", 50),
    ("h", "3-wood", 134.206, 92.967, -10.6, -2.164, "test2", 50),
    ("v", "3-wood", 122.292, 93.985, 16.0, 19.045, "test2", 51),
    ("h", "3-wood", 122.292, 93.985, -5.3, -6.331, "test2", 51),
    ("v", "3-wood", 135.428, 91.643, 15.7, 14.753, "test2", 52),
    ("h", "3-wood", 135.428, 91.643, -9.9, -0.919, "test2", 52),
    ("v", "3-wood", 129.522, 91.745, 32.8, 15.717, "test2", 53),
    ("h", "3-wood", 129.522, 91.745, -11.6, -3.257, "test2", 53),
    ("v", "3-wood", 120.663, 81.562, 15.8, 10.941, "test2", 54),
    ("h", "3-wood", 120.663, 81.562, 5.0, -10.797, "test2", 54),
    ("v", "3-wood", 131.864, 88.996, 29.6, 5.834, "test2", 55),
    ("h", "3-wood", 131.864, 88.996, -6.9, -12.505, "test2", 55),
    ("v", "3-wood", 128.504, 86.348, 14.7, 11.435, "test2", 56),
    ("h", "3-wood", 128.504, 86.348, -2.4, -5.404, "test2", 56),
    ("v", "3-wood", 77.897, 63.641, 25.6, 23.937, "test2", 57),
    ("h", "3-wood", 77.897, 63.641, -6.5, -1.868, "test2", 57),
    ("v", "3-wood", 126.366, 86.246, 11.6, 6.239, "test2", 58),
    ("h", "3-wood", 126.366, 86.246, -7.9, -11.365, "test2", 58),
    ("v", "7-iron", 107.324, 77.184, 12.0, 14.783, "test2", 28),
    ("h", "7-iron", 107.324, 77.184, 6.5, 5.088, "test2", 28),
    ("v", "7-iron", 115.776, 78.609, 21.3, 10.857, "test2", 29),
    ("h", "7-iron", 115.776, 78.609, 12.7, -2.742, "test2", 29),
    ("v", "7-iron", 121.071, 82.886, 5.0, 15.103, "test2", 30),
    ("h", "7-iron", 121.071, 82.886, -7.0, -3.298, "test2", 30),
    ("v", "7-iron", 109.157, 80.442, 10.5, 14.274, "test2", 31),
    ("h", "7-iron", 109.157, 80.442, 0.0, 5.717, "test2", 31),
    ("v", "7-iron", 122.394, 83.599, 24.6, 13.259, "test2", 32),
    ("h", "7-iron", 122.394, 83.599, -7.8, -3.078, "test2", 32),
    ("v", "7-iron", 95.614, 80.849, 15.7, 6.326, "test2", 33),
    ("h", "7-iron", 95.614, 80.849, 14.0, 16.062, "test2", 33),
    ("v", "7-iron", 121.783, 84.515, 12.4, 13.597, "test2", 34),
    ("h", "7-iron", 121.783, 84.515, 6.5, -4.944, "test2", 34),
    ("v", "7-iron", 116.794, 82.071, 15.1, 16.338, "test2", 35),
    ("h", "7-iron", 116.794, 82.071, -11.5, 0.865, "test2", 35),
    ("v", "7-iron", 96.327, 68.732, 24.6, 19.084, "test2", 36),
    ("h", "7-iron", 96.327, 68.732, 5.6, -4.804, "test2", 36),
    ("v", "7-iron", 99.585, 70.056, 18.7, 21.728, "test2", 37),
    ("h", "7-iron", 99.585, 70.056, 2.8, -2.319, "test2", 37),
    ("v", "7-iron", 98.669, 67.103, 25.4, 20.168, "test2", 38),
    ("h", "7-iron", 98.669, 67.103, -0.7, -2.705, "test2", 38),
    ("v", "7-iron", 74.536, 57.226, 23.1, 15.104, "test2", 39),
    ("h", "7-iron", 74.536, 57.226, -5.4, 14.738, "test2", 39),
    ("v", "7-iron", 86.857, 67.51, 12.6, 13.983, "test2", 40),
    ("h", "7-iron", 86.857, 67.51, 8.7, 8.68, "test2", 40),
    ("v", "7-iron", 104.778, 71.176, 15.0, 18.843, "test2", 41),
    ("h", "7-iron", 104.778, 71.176, -3.3, -8.309, "test2", 41),
    ("v", "7-iron", 92.661, 67.205, 8.9, 8.749, "test2", 42),
    ("h", "7-iron", 92.661, 67.205, -0.9, 13.599, "test2", 42),
    ("v", "7-iron", 87.875, 65.372, 14.4, 8.423, "test2", 43),
    ("h", "7-iron", 87.875, 65.372, 0.9, 12.522, "test2", 43),
    ("v", "7-iron", 99.076, 68.121, 19.3, 1.16, "test2", 44),
    ("h", "7-iron", 99.076, 68.121, -14.7, -3.205, "test2", 44),
    ("v", "7-iron", 97.447, 68.427, 16.3, 1.933, "test2", 45),
    ("h", "7-iron", 97.447, 68.427, -3.4, 2.729, "test2", 45),
    ("v", "9-iron", 100.502, 81.562, 21.1, 17.462, "test2", 1),
    ("h", "9-iron", 100.502, 81.562, 2.3, -6.023, "test2", 1),
    ("v", "9-iron", 107.833, 83.497, 6.2, 17.585, "test2", 2),
    ("h", "9-iron", 107.833, 83.497, 2.6, -4.658, "test2", 2),
    ("v", "9-iron", 107.833, 72.5, 6.3, 19.906, "test2", 3),
    ("h", "9-iron", 107.833, 72.5, -6.4, -4.289, "test2", 3),
    ("v", "9-iron", 104.473, 70.361, 10.7, 17.412, "test2", 5),
    ("h", "9-iron", 104.473, 70.361, 7.9, -4.29, "test2", 5),
    ("v", "9-iron", 100.909, 78.609, 13.8, 3.86, "test2", 7),
    ("h", "9-iron", 100.909, 78.609, 6.9, 0.621, "test2", 7),
    ("v", "9-iron", 92.763, 72.703, 23.4, 25.68, "test2", 9),
    ("h", "9-iron", 92.763, 72.703, 4.8, -7.877, "test2", 9),
    ("v", "9-iron", 73.314, 61.706, 22.0, 17.305, "test2", 10),
    ("h", "9-iron", 73.314, 61.706, 6.6, 20.184, "test2", 10),
    ("v", "9-iron", 99.687, 67.001, 15.5, 23.569, "test2", 11),
    ("h", "9-iron", 99.687, 67.001, -7.1, -4.358, "test2", 11),
    ("v", "9-iron", 81.257, 61.197, 13.1, 24.83, "test2", 12),
    ("h", "9-iron", 81.257, 61.197, -0.3, -2.861, "test2", 12),
    ("v", "9-iron", 89.097, 63.641, 21.2, 25.118, "test2", 13),
    ("h", "9-iron", 89.097, 63.641, -1.6, -3.24, "test2", 13),
    ("v", "9-iron", 88.792, 64.965, 11.8, 9.096, "test2", 14),
    ("h", "9-iron", 88.792, 64.965, 4.5, 9.151, "test2", 14),
    ("v", "9-iron", 76.064, 51.015, 8.0, 17.449, "test2", 15),
    ("h", "9-iron", 76.064, 51.015, -0.1, 16.721, "test2", 15),
    ("v", "9-iron", 70.565, 58.55, 16.2, 18.087, "test2", 16),
    ("h", "9-iron", 70.565, 58.55, -5.1, 19.147, "test2", 16),
    ("v", "9-iron", 64.965, 53.866, 8.4, 5.392, "test2", 17),
    ("h", "9-iron", 64.965, 53.866, -5.3, -0.594, "test2", 17),
    ("v", "9-iron", 86.348, 66.187, 20.7, 24.081, "test2", 18),
    ("h", "9-iron", 86.348, 66.187, -4.2, -3.686, "test2", 18),
    ("v", "9-iron", 91.643, 66.594, 12.3, 24.283, "test2", 19),
    ("h", "9-iron", 91.643, 66.594, -2.7, -3.53, "test2", 19),
    ("v", "9-iron", 87.672, 67.51, 13.6, 8.543, "test2", 20),
    ("h", "9-iron", 87.672, 67.51, 10.6, 12.138, "test2", 20),
    ("v", "9-iron", 90.217, 68.63, 15.8, 23.735, "test2", 21),
    ("h", "9-iron", 90.217, 68.63, -0.8, -3.773, "test2", 21),
    ("v", "9-iron", 78.609, 64.557, 16.4, 23.197, "test2", 22),
    ("h", "9-iron", 78.609, 64.557, 10.0, 7.469, "test2", 22),
    ("v", "9-iron", 54.782, 38.083, 37.5, 5.152, "test2", 25),
    ("h", "9-iron", 54.782, 38.083, 0.0, -1.1, "test2", 25),
    ("v", "9-iron", 52.949, 40.323, 35.3, 10.591, "test2", 26),
    ("h", "9-iron", 52.949, 40.323, 2.0, -4.644, "test2", 26),
    ("v", "9-iron", 72.296, 55.393, 11.6, 11.214, "test2", 27),
    ("h", "9-iron", 72.296, 55.393, -8.1, 13.064, "test2", 27),
)

_SAMPLES: tuple[TrackmanCalibrationSample, ...] = tuple(
    TrackmanCalibrationSample(*sample) for sample in _RAW_SAMPLES
)


def training_samples() -> tuple[TrackmanCalibrationSample, ...]:
    """Return the baked TrackMan comparison samples used by the experiment."""
    return _SAMPLES


def _club_value(club: object) -> str:
    if isinstance(club, Enum):
        return str(club.value)
    return str(club or "unknown")


def _feature_distance(
    sample: TrackmanCalibrationSample,
    club: str,
    ball_speed_mph: float,
    club_speed_mph: float,
    raw_angle_deg: float,
) -> float:
    club_penalty = 2.0 if sample.club != club else 0.0
    return math.sqrt(
        ((sample.raw_angle_deg - raw_angle_deg) / 8.0) ** 2
        + ((sample.ball_speed_mph - ball_speed_mph) / 10.0) ** 2
        + ((sample.club_speed_mph - club_speed_mph) / 10.0) ** 2
        + club_penalty**2
    )


def calibrate_angle_with_metadata(
    *,
    axis: str,
    raw_angle_deg: float,
    club: object,
    ball_speed_mph: float,
    club_speed_mph: float | None,
    neighbors: int = 3,
    max_neighbor_distance: float | None = 2.0,
    samples: Iterable[TrackmanCalibrationSample] = _SAMPLES,
) -> TrackmanCalibrationResult:
    """Return the experimental TrackMan-calibrated K-LD7 angle and decision.

    Exact matches are snapped to the saved TrackMan value. New live shots use
    inverse-distance weighted nearest neighbors within the same axis, using
    leave-one-out tuned feature scales from the two comparison sessions. If the
    nearest sample is outside the calibrated training manifold, return the raw
    angle rather than applying a weak extrapolation.
    """
    axis_key = axis.lower()[:1]
    club_key = _club_value(club)
    club_speed = float(club_speed_mph or 0.0)
    candidates = [sample for sample in samples if sample.axis == axis_key]
    if not candidates:
        return TrackmanCalibrationResult(
            angle_deg=round(float(raw_angle_deg), 1),
            raw_angle_deg=float(raw_angle_deg),
            decision="no_axis_samples",
            nearest_distance=None,
            nearest_session=None,
            nearest_shot_number=None,
            nearest_axis=None,
            nearest_club=None,
        )

    scored = sorted(
        (
            (
                _feature_distance(
                    sample,
                    club_key,
                    float(ball_speed_mph),
                    club_speed,
                    float(raw_angle_deg),
                ),
                sample,
            )
            for sample in candidates
        ),
        key=lambda item: item[0],
    )
    best_distance, best_sample = scored[0]
    if best_distance < 1e-9:
        return TrackmanCalibrationResult(
            angle_deg=round(best_sample.trackman_angle_deg, 1),
            raw_angle_deg=float(raw_angle_deg),
            decision="exact_match",
            nearest_distance=best_distance,
            nearest_session=best_sample.session,
            nearest_shot_number=best_sample.shot_number,
            nearest_axis=best_sample.axis,
            nearest_club=best_sample.club,
        )
    if max_neighbor_distance is not None and best_distance > max_neighbor_distance:
        return TrackmanCalibrationResult(
            angle_deg=round(float(raw_angle_deg), 1),
            raw_angle_deg=float(raw_angle_deg),
            decision="outside_training_manifold",
            nearest_distance=best_distance,
            nearest_session=best_sample.session,
            nearest_shot_number=best_sample.shot_number,
            nearest_axis=best_sample.axis,
            nearest_club=best_sample.club,
        )

    nearest = scored[: max(1, int(neighbors))]
    weighted_sum = 0.0
    total_weight = 0.0
    for distance, sample in nearest:
        weight = 1.0 / max(distance, 0.05) ** 2
        weighted_sum += sample.trackman_angle_deg * weight
        total_weight += weight
    if total_weight <= 0:
        return TrackmanCalibrationResult(
            angle_deg=round(float(raw_angle_deg), 1),
            raw_angle_deg=float(raw_angle_deg),
            decision="zero_weight",
            nearest_distance=best_distance,
            nearest_session=best_sample.session,
            nearest_shot_number=best_sample.shot_number,
            nearest_axis=best_sample.axis,
            nearest_club=best_sample.club,
        )
    return TrackmanCalibrationResult(
        angle_deg=round(weighted_sum / total_weight, 1),
        raw_angle_deg=float(raw_angle_deg),
        decision="fallback_knn",
        nearest_distance=best_distance,
        nearest_session=best_sample.session,
        nearest_shot_number=best_sample.shot_number,
        nearest_axis=best_sample.axis,
        nearest_club=best_sample.club,
    )


def calibrate_angle(
    *,
    axis: str,
    raw_angle_deg: float,
    club: object,
    ball_speed_mph: float,
    club_speed_mph: float | None,
    neighbors: int = 3,
    max_neighbor_distance: float | None = 2.0,
    samples: Iterable[TrackmanCalibrationSample] = _SAMPLES,
) -> float:
    """Return only the experimental TrackMan-calibrated K-LD7 angle."""
    return calibrate_angle_with_metadata(
        axis=axis,
        raw_angle_deg=raw_angle_deg,
        club=club,
        ball_speed_mph=ball_speed_mph,
        club_speed_mph=club_speed_mph,
        neighbors=neighbors,
        max_neighbor_distance=max_neighbor_distance,
        samples=samples,
    ).angle_deg
