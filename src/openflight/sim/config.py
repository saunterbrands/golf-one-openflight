"""Simulator-connector configuration: config/sim.json.

A single file lists every connector; the server streams to all that are
``enabled`` — but only when the sim feature is turned on at launch (``--sim``).

A connector's ``type`` is the *product*: gspro (OpenConnect V1 on 921) or
opengolfsim (reached via its Developer API on 3111, which speaks OpenConnect).
Both ride the shared OpenConnect codec; they differ only in name + default port.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_CONFIG_PATH = Path("config/sim.json")

KNOWN_TYPES: Tuple[str, ...] = ("gspro", "opengolfsim")

# Per-type defaults applied when a field is absent from the file.
_DEFAULTS: Dict[str, dict] = {
    "gspro": {"port": 921, "units": "Yards", "device_id": "OpenFlight",
              "heartbeat_interval_s": 5.0},
    "opengolfsim": {"port": 3111, "units": "Yards", "device_id": "OpenFlight",
                    "heartbeat_interval_s": 5.0},
}


@dataclass
class ConnectorConfig:
    """One resolved simulator endpoint."""

    type: str
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 0
    units: str = "Yards"
    device_id: str = "OpenFlight"
    heartbeat_interval_s: float = 5.0


def _with_defaults(connector_type: str, data: dict) -> ConnectorConfig:
    base = dict(_DEFAULTS[connector_type])
    base.update(data)
    return ConnectorConfig(
        type=connector_type,
        enabled=bool(base.get("enabled", False)),
        host=str(base.get("host", "127.0.0.1")),
        port=int(base["port"]),
        units=str(base.get("units", "Yards")),
        device_id=str(base.get("device_id", "OpenFlight")),
        heartbeat_interval_s=float(base.get("heartbeat_interval_s", 5.0)),
    )


def load_sim_config(config_path: Path = DEFAULT_CONFIG_PATH) -> List[ConnectorConfig]:
    """Resolve the enabled connector configs from the file (only enabled ones).

    Gating the whole feature on/off is the caller's job (the ``--sim`` flag);
    this just reads which connectors the file enables.
    """
    if not config_path.exists():
        return []
    data = json.loads(config_path.read_text(encoding="utf-8"))
    cfgs: List[ConnectorConfig] = []
    for entry in data.get("connectors", []):
        ctype = entry.get("type")
        if ctype not in KNOWN_TYPES:
            raise ValueError(f"unknown simulator type in {config_path}: {ctype!r}")
        cfg = _with_defaults(ctype, entry)
        if cfg.enabled:
            cfgs.append(cfg)
    return cfgs
