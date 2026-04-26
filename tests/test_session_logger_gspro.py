"""Tests for new GSPro entry types in SessionLogger."""
import json

from openflight.session_logger import SessionLogger


def _read_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_log_gspro_send(tmp_path):
    log = SessionLogger(log_dir=tmp_path, location="range")
    log.start_session()
    payload = {"BallData": {"Speed": 140.0}}
    provenance = {"BallData.Speed": "measured"}
    log.log_gspro_send(shot_number=1, payload=payload, provenance=provenance)
    log.end_session()
    entries = _read_jsonl(log.session_path)
    sends = [e for e in entries if e["type"] == "gspro_send"]
    assert len(sends) == 1
    assert sends[0]["shot_number"] == 1
    assert sends[0]["payload"] == payload
    assert sends[0]["provenance"] == provenance


def test_log_gspro_status(tmp_path):
    log = SessionLogger(log_dir=tmp_path, location="range")
    log.start_session()
    log.log_gspro_status(state="connected", host="10.0.0.5", port=921, message="")
    log.end_session()
    entries = _read_jsonl(log.session_path)
    statuses = [e for e in entries if e["type"] == "gspro_status"]
    assert len(statuses) == 1
    assert statuses[0]["state"] == "connected"
    assert statuses[0]["host"] == "10.0.0.5"


def test_log_gspro_player(tmp_path):
    log = SessionLogger(log_dir=tmp_path, location="range")
    log.start_session()
    log.log_gspro_player(handed="LH", club="I7")
    log.end_session()
    entries = _read_jsonl(log.session_path)
    plays = [e for e in entries if e["type"] == "gspro_player"]
    assert len(plays) == 1
    assert plays[0]["handed"] == "LH"
    assert plays[0]["club"] == "I7"
