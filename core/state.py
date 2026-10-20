"""
core/state.py
-------------
Power-state detection and adaptive sampling interval.

All projects call `get_sampling_interval()` at the top of their main loop so
they automatically throttle on battery without any per-project code.
"""

import psutil
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PowerState:
    on_battery: bool
    battery_percent: Optional[float]  # None if no battery (desktop)
    power_plugged: bool


def get_power_state() -> PowerState:
    """Return the current power source and battery level."""
    battery = psutil.sensors_battery()
    if battery is None:
        # Desktop machine — always treat as AC
        return PowerState(on_battery=False, battery_percent=None, power_plugged=True)
    return PowerState(
        on_battery=not battery.power_plugged,
        battery_percent=round(battery.percent, 1),
        power_plugged=battery.power_plugged,
    )


def get_sampling_interval(ac_interval: float = 1.0, dc_interval: float = 4.0) -> float:
    """
    Return the appropriate camera polling interval in seconds.

    - AC (plugged in): `ac_interval`  → higher responsiveness
    - DC (battery):    `dc_interval`  → negligible battery impact
    """
    state = get_power_state()
    return dc_interval if state.on_battery else ac_interval


if __name__ == "__main__":
    state = get_power_state()
    interval = get_sampling_interval()
    source = "Battery" if state.on_battery else "AC"
    pct = f" ({state.battery_percent}%)" if state.battery_percent is not None else ""
    print(f"Power source : {source}{pct}")
    print(f"Poll interval: {interval}s")
