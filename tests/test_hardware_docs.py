"""Safety checks for user-facing hardware wiring documentation."""

from pathlib import Path


def test_ops243_j3_ground_is_documented_as_pin_10():
    repo_root = Path(__file__).resolve().parents[1]
    wiring = (repo_root / "docs/sound-trigger-wiring.md").read_text(
        encoding="utf-8"
    )
    parts = (repo_root / "docs/PARTS.md").read_text(encoding="utf-8")

    for document in (wiring, parts):
        assert "J3 Pin 10" in document
        assert "J3 Pin 1)" not in document
        assert "J3 P1)" not in document

    assert "J3 pin 3 is third from the right" in wiring
    assert "J3 pin 10 is at the far left" in wiring
