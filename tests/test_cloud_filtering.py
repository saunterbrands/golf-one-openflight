"""Tests for the openflight-cloud client-side filtering (raw-ADC strip)."""

import gzip
import json
import uuid

import pytest

from openflight.cloud import filtering as flt


def _line(entry_type, **fields):
    return json.dumps({"ts": "2026-06-14T00:00:00", "type": entry_type, **fields})


class TestResolveSessionId:
    def test_uses_embedded_session_uuid_lowercased(self):
        u = "1F0E9C2A-7B3D-4E5F-8A9B-0C1D2E3F4A5B"
        lines = [_line("session_start", session_uuid=u)]
        assert flt.resolve_session_id(lines, "dev-1", "session_x.jsonl") == u.lower()

    def test_uuid5_fallback_when_no_session_uuid(self):
        lines = [_line("session_start")]
        result = flt.resolve_session_id(lines, "dev-1", "session_x.jsonl")
        expected = str(uuid.uuid5(flt.SESSION_NAMESPACE, "dev-1:session_x.jsonl"))
        assert result == expected

    def test_uuid5_fallback_is_deterministic(self):
        a = flt.resolve_session_id([], "dev-1", "session_x.jsonl")
        b = flt.resolve_session_id([], "dev-1", "session_x.jsonl")
        assert a == b

    def test_uuid5_fallback_differs_by_device(self):
        a = flt.resolve_session_id([], "dev-1", "session_x.jsonl")
        b = flt.resolve_session_id([], "dev-2", "session_x.jsonl")
        assert a != b


class TestFilterSessionLines:
    def test_keeps_only_allowlisted_types(self):
        lines = [
            _line("session_start", session_uuid="u"),
            _line("rolling_buffer_capture", i_samples=[1, 2, 3]),
            _line("shot_detected", ball_speed_mph=100),
            _line("iq_blocks", blocks=[]),
            _line("trigger_event", accepted=True),
            _line("session_end"),
        ]
        result = flt.filter_session_lines(lines, device_id="dev-1")
        kept_types = [json.loads(line)["type"] for line in result.kept_lines]
        assert kept_types == [
            "session_start",
            "shot_detected",
            "trigger_event",
            "session_end",
        ]

    def test_keeps_both_error_and_session_error(self):
        lines = [
            _line("error", error="boom"),
            _line("session_error", error="boom2"),
        ]
        result = flt.filter_session_lines(lines, device_id="dev-1")
        kept_types = [json.loads(line)["type"] for line in result.kept_lines]
        assert kept_types == ["error", "session_error"]

    def test_drops_unknown_future_type_by_default(self):
        lines = [_line("some_future_heavy_type", data="x" * 10)]
        result = flt.filter_session_lines(lines, device_id="dev-1")
        assert result.kept_lines == []

    def test_drops_kept_line_over_32kb_and_counts_it(self):
        big = _line("shot_detected", note="x" * (33 * 1024))
        small = _line("shot_detected", ball_speed_mph=90)
        result = flt.filter_session_lines([big, small], device_id="dev-1")
        assert result.dropped_oversize == 1
        assert len(result.kept_lines) == 1

    def test_ignores_blank_and_unparseable_lines(self):
        lines = ["", "   ", "not json", _line("shot_detected", ball_speed_mph=90)]
        result = flt.filter_session_lines(lines, device_id="dev-1")
        assert len(result.kept_lines) == 1

    def test_manifest_has_expected_shape(self):
        lines = [
            _line("session_start", session_uuid="u"),
            _line("shot_detected", ball_speed_mph=90),
        ]
        result = flt.filter_session_lines(lines, device_id="dev-7", client_version="9.9.9")
        m = result.manifest
        assert m["type"] == "upload_manifest"
        assert m["format_version"] == 1
        assert m["client_version"] == "9.9.9"
        assert m["device_id"] == "dev-7"
        assert m["filtered"] is True
        assert set(m["kept_entry_types"]) == {"session_start", "shot_detected"}

    def test_kept_entry_types_are_sorted_and_unique(self):
        lines = [
            _line("shot_detected"),
            _line("shot_detected"),
            _line("session_start"),
        ]
        result = flt.filter_session_lines(lines, device_id="d")
        assert result.manifest["kept_entry_types"] == ["session_start", "shot_detected"]


class TestBuildUploadBody:
    def test_body_is_gzip_with_manifest_first(self):
        lines = [
            _line("session_start", session_uuid="u"),
            _line("shot_detected", ball_speed_mph=90),
        ]
        result = flt.filter_session_lines(lines, device_id="dev-1")
        body = flt.build_upload_body(result)

        ndjson = gzip.decompress(body).decode("utf-8")
        out_lines = ndjson.strip().split("\n")
        first = json.loads(out_lines[0])
        assert first["type"] == "upload_manifest"
        assert json.loads(out_lines[1])["type"] == "session_start"
        assert json.loads(out_lines[2])["type"] == "shot_detected"

    def test_raises_when_gzip_exceeds_cap(self):
        result = flt.FilterResult(
            manifest={"type": "upload_manifest"},
            kept_lines=[_line("shot_detected", ball_speed_mph=90)],
            dropped_oversize=0,
        )
        # 1-byte caps make any real body too large.
        with pytest.raises(flt.BodyTooLargeError):
            flt.build_upload_body(result, max_gzip_bytes=1, max_inflated_bytes=1_000_000)

    def test_raises_when_inflated_exceeds_cap(self):
        result = flt.FilterResult(
            manifest={"type": "upload_manifest"},
            kept_lines=[_line("shot_detected", ball_speed_mph=90)],
            dropped_oversize=0,
        )
        with pytest.raises(flt.BodyTooLargeError):
            flt.build_upload_body(result, max_gzip_bytes=1_000_000, max_inflated_bytes=1)
