"""Fleet simulation loop and runner.

Purpose: Ticks periodically against an injected clock, generating and dispatching fleet telemetry.
Inputs: Fleet profiles, clock instance, duration and speed parameters.
Outputs: Telemetry messages sent to publisher or callbacks.
"""

from __future__ import annotations

import argparse
import random
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from backend.common.clock import Clock, FakeClock, SystemClock
from backend.common.config import load_settings
from backend.common.logging import configure_logging, get_logger
from backend.common.schemas import TelemetryMessage

from simulator.devices import DeviceProfile, make_fleet
from simulator.generator import next_telemetry
from simulator.publisher import TelemetryPublisher

logger = get_logger(__name__)

DEFAULT_TICK_INTERVAL_S: float = 15.0


class SimulationRunner:
    """Orchestrates multi-device fleet telemetry generation across time ticks."""

    def __init__(
        self,
        fleet: list[DeviceProfile],
        clock: Clock,
        publisher: TelemetryPublisher | None = None,
        seed: int = 42,
        tick_interval_s: float = DEFAULT_TICK_INTERVAL_S,
        fault_hook: Callable[[TelemetryMessage, datetime], TelemetryMessage | None] | None = None,
    ) -> None:
        self.fleet = fleet
        self.clock = clock
        self.publisher = publisher
        self.tick_interval_s = tick_interval_s
        self.fault_hook = fault_hook
        self._rngs: dict[str, random.Random] = {
            profile.device_id: random.Random(seed + idx)  # nosec: B311
            for idx, profile in enumerate(fleet)
        }
        self._device_states: dict[str, dict[str, Any]] = {
            profile.device_id: {} for profile in fleet
        }

    def step(self) -> list[TelemetryMessage]:
        """Execute one simulation step across the entire fleet at the current clock time."""
        current_time = self.clock.now()
        messages: list[TelemetryMessage] = []

        for profile in self.fleet:
            rng = self._rngs[profile.device_id]
            state = self._device_states[profile.device_id]
            msg = next_telemetry(profile, state, current_time, rng)

            if self.fault_hook is not None:
                faulted_msg = self.fault_hook(msg, current_time)
                if faulted_msg is None:
                    continue  # Comm dropout: suppressed
                msg = faulted_msg

            messages.append(msg)

            if self.publisher is not None:
                self.publisher.publish(msg)

        return messages

    def run_simulation(
        self,
        duration_s: float,
        on_message: Callable[[TelemetryMessage], None] | None = None,
    ) -> int:
        """Run simulation for a fixed duration in seconds using the injected clock.

        Args:
            duration_s: Total simulated duration in seconds.
            on_message: Optional callback invoked for each generated message.

        Returns:
            Total count of generated telemetry messages.
        """
        steps = int(duration_s // self.tick_interval_s)
        total_messages = 0

        for _ in range(steps):
            messages = self.step()
            total_messages += len(messages)

            if on_message is not None:
                for msg in messages:
                    on_message(msg)

            if isinstance(self.clock, FakeClock):
                self.clock.advance(timedelta(seconds=self.tick_interval_s))

        return total_messages


def run_cli() -> None:
    """CLI runner supporting speed factor, duration, and dry-run."""
    parser = argparse.ArgumentParser(description="IIR Fleet Telemetry Simulation Runner")
    parser.add_argument("--speed", type=float, default=1.0, help="Simulation speed multiplier")
    parser.add_argument(
        "--duration", type=float, default=None, help="Duration in seconds (e.g. 86400)"
    )
    parser.add_argument("--devices", type=int, default=20, help="Number of inverters in fleet")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument(
        "--dry-run", action="store_true", help="Generate telemetry without connecting to MQTT"
    )

    args = parser.parse_args()
    configure_logging()

    fleet = make_fleet(args.devices, seed=args.seed)
    clock = SystemClock()
    publisher = None

    if not args.dry_run:
        settings = load_settings()
        publisher = TelemetryPublisher(settings)
        publisher.connect()

    runner = SimulationRunner(fleet=fleet, clock=clock, publisher=publisher, seed=args.seed)
    logger.info("Starting simulation for %d devices (speed=%.1fx)...", len(fleet), args.speed)

    tick_sleep = DEFAULT_TICK_INTERVAL_S / max(0.001, args.speed)
    elapsed = 0.0

    try:
        while args.duration is None or elapsed < args.duration:
            messages = runner.step()
            total_power_kw = sum(m.ac_power_w for m in messages) / 1000.0
            sample = messages[0]
            logger.info(
                "[Tick %04d] %s | %d inverters | Total Fleet: %.2f kW | Sample %s: %.1f W, %.1f V, %.1f C, relay=%s",
                int(elapsed // DEFAULT_TICK_INTERVAL_S) + 1,
                sample.ts.strftime("%Y-%m-%d %H:%M:%S UTC"),
                len(messages),
                total_power_kw,
                sample.device_id,
                sample.ac_power_w,
                sample.grid_voltage_v,
                sample.temperature_c,
                sample.relay_state,
            )
            elapsed += DEFAULT_TICK_INTERVAL_S
            time.sleep(tick_sleep)
    except KeyboardInterrupt:
        logger.info("Simulation halted by user.")
    finally:
        if publisher is not None:
            publisher.disconnect()


if __name__ == "__main__":
    run_cli()
