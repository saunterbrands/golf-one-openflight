"""State-machine tests for the local Chromium-to-FUSE shot relay."""

from dataclasses import replace

import pytest

from openflight.launch_monitor import ClubType
from openflight.opengolfsim.browser_relay import (
    BrowserShotRelay,
    InvalidBrowserSession,
)
from openflight.opengolfsim.web_bridge import build_web_shot_payload
from openflight.sim.types import ResolvedShot


def _resolved_shot(**overrides) -> ResolvedShot:
    shot = ResolvedShot(
        shot_number=7,
        ball_speed_mph=143.26,
        vla=11.84,
        hla=-2.26,
        total_spin_rpm=2487.6,
        spin_axis_deg=4.24,
        back_spin_rpm=2480.0,
        side_spin_rpm=184.0,
        carry_yards=239.0,
        club_path_deg=-1.0,
        club=ClubType.DRIVER,
        provenance={
            "ball_speed": "measured",
            "vla": "measured",
            "hla": "measured",
            "total_spin": "estimated",
            "spin_axis": "measured",
        },
    )
    return replace(shot, **overrides)


def test_browser_payload_matches_fuse_contract_and_inverts_spin_axis_once():
    assert build_web_shot_payload(_resolved_shot()) == {
        "type": "shot",
        "unit": "imperial",
        "shot": {
            "ballSpeed": 143.3,
            "verticalLaunchAngle": 11.8,
            "horizontalLaunchAngle": -2.3,
            "spinSpeed": 2488.0,
            "spinAxis": -4.2,
        },
    }


def test_browser_relay_delivers_once_and_records_completed_result():
    relay = BrowserShotRelay(poll_timeout_s=0.001)
    session = relay.open_session()
    payload = build_web_shot_payload(_resolved_shot())

    published = relay.publish(payload)

    assert published.accepted is True
    assert published.sequence == 1
    delivery = relay.poll(
        session_id=session["session_id"],
        after=session["cursor"],
    )
    assert delivery == [{"sequence": 1, "payload": payload}]

    relay.acknowledge(
        session_id=session["session_id"],
        sequence=1,
        state="posted",
    )
    assert (
        relay.poll(
            session_id=session["session_id"],
            after=1,
        )
        == []
    )

    relay.acknowledge(
        session_id=session["session_id"],
        sequence=1,
        state="completed",
        result={"carry": 231.4, "total": 247.2, "surface": "fairway"},
    )
    status = relay.status()
    assert status["game_state"] == "ready"
    assert status["last_delivery"] == {
        "sequence": 1,
        "state": "completed",
        "result": {"carry": 231.4, "total": 247.2, "surface": "fairway"},
    }


def test_browser_relay_rejects_a_second_shot_while_one_is_in_flight():
    relay = BrowserShotRelay(poll_timeout_s=0.001)
    session = relay.open_session()
    first = relay.publish(build_web_shot_payload(_resolved_shot()))
    relay.acknowledge(
        session_id=session["session_id"],
        sequence=first.sequence,
        state="posted",
    )

    second = relay.publish(build_web_shot_payload(_resolved_shot(ball_speed_mph=151.0)))

    assert second.accepted is False
    assert second.reason == "OpenGolfSim is still playing the previous shot"


def test_new_browser_session_skips_stale_shots_and_invalidates_old_tab():
    relay = BrowserShotRelay(poll_timeout_s=0.001)
    old_session = relay.open_session()
    published = relay.publish(build_web_shot_payload(_resolved_shot()))
    assert published.accepted

    new_session = relay.open_session()

    assert new_session["cursor"] == published.sequence
    assert (
        relay.poll(
            session_id=new_session["session_id"],
            after=new_session["cursor"],
        )
        == []
    )
    with pytest.raises(InvalidBrowserSession):
        relay.poll(
            session_id=old_session["session_id"],
            after=old_session["cursor"],
        )


def test_browser_session_expires_without_heartbeat():
    now = [100.0]
    relay = BrowserShotRelay(
        session_ttl_s=5.0,
        poll_timeout_s=0.001,
        clock=lambda: now[0],
    )
    session = relay.open_session()
    assert relay.is_active()

    now[0] = 105.1

    assert relay.is_active() is False
    with pytest.raises(InvalidBrowserSession):
        relay.poll(
            session_id=session["session_id"],
            after=session["cursor"],
        )


def test_in_flight_shot_times_out_without_locking_the_next_real_shot():
    now = [100.0]
    relay = BrowserShotRelay(
        shot_timeout_s=10.0,
        poll_timeout_s=0.001,
        clock=lambda: now[0],
    )
    session = relay.open_session()
    first = relay.publish(build_web_shot_payload(_resolved_shot()))
    relay.acknowledge(
        session_id=session["session_id"],
        sequence=first.sequence,
        state="posted",
    )

    now[0] = 110.1

    status = relay.status()
    assert status["game_state"] == "ready"
    assert status["last_delivery"] == {
        "sequence": 1,
        "state": "error",
        "reason": "OpenGolfSim did not finish the shot in time",
    }
    second = relay.publish(build_web_shot_payload(_resolved_shot(ball_speed_mph=151.0)))
    assert second.accepted is True
    assert second.sequence == 2


def test_late_posted_ack_cannot_downgrade_a_completed_result():
    relay = BrowserShotRelay(poll_timeout_s=0.001)
    session = relay.open_session()
    published = relay.publish(build_web_shot_payload(_resolved_shot()))
    relay.acknowledge(
        session_id=session["session_id"],
        sequence=published.sequence,
        state="posted",
    )
    completed = relay.acknowledge(
        session_id=session["session_id"],
        sequence=published.sequence,
        state="completed",
        result={"carry": 231.4},
    )

    late = relay.acknowledge(
        session_id=session["session_id"],
        sequence=published.sequence,
        state="posted",
    )

    assert late == completed
    assert late["last_delivery"] == {
        "sequence": published.sequence,
        "state": "completed",
        "result": {"carry": 231.4},
    }
