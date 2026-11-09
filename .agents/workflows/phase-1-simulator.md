---
description: Phase 1 - build the 20-device MQTT telemetry simulator with seeded, reproducible output
---

# Phase 1: Telemetry simulator

## Preconditions
- Phase 0 is DONE in `docs/progress.md`.

## Steps
1. Create branch `phase/1-simulator`.
2. Add to `src/iir/common/schemas.py` the `TelemetryMessage` model: frozen, `extra="forbid"`. Fields: `device_id` (matches `^INV-\d{2}$`), `ts` (timezone-aware UTC), `ac_power_w` (0 to 10000), `dc_voltage_v` (0 to 1000), `grid_voltage_v` (0 to 300), `temperature_c` (-40 to 120), `relay_state` (`closed` or `open`), `status` (`normal`, `warning`, or `error`).
3. Create `src/iir/common/clock.py` with a `Clock` protocol, `SystemClock`, and `FakeClock` (settable and advanceable).
4. Create `src/iir/simulator/devices.py`. `DeviceProfile` holds the device ID, a rated power between 2000 and 6000 W, a panel count, and an ambient offset. `make_fleet(n, seed)` returns 20 profiles, reproducible from the seed.
5. Create `src/iir/simulator/curves.py` as pure functions. `irradiance_factor(local_hour)` returns 0 at night, peaks at 1.0 near 12:30, and rises smoothly from 6:00. `expected_power(profile, hour)` returns watts. `expected_temperature(power_w, ambient_c)` returns a module temperature that rises with power and is capped.
6. Create `src/iir/simulator/generator.py` with a pure function `next_telemetry(profile, state, ts, rng)`. Use seeded Gaussian noise of about 1 percent on power, about 1 V on grid voltage, and a small amount on temperature. Relay is `closed` in daylight and `open` at night. Status is always `normal` in this phase.
7. Create `src/iir/simulator/publisher.py`. It wraps paho-mqtt, reads credentials from config, uses TLS when `MQTT_TLS=true`, publishes JSON to `fleet/inverter/{device_id}/telemetry` at QoS 1, and refuses payloads over 2 KB.
8. Create `src/iir/simulator/runner.py`. It ticks every 15 seconds on the injected clock, generates and validates each message, and publishes it. It supports a `--speed` factor and a `--duration` option.
9. Create `src/iir/simulator/replay.py`. It writes a run to `data/raw/sim/run_{seed}.jsonl`, so the pipeline can replay without a broker.

## Acceptance tests
- Curve: `irradiance_factor(0) == 0`, `irradiance_factor(12.5)` is within 0.01 of 1.0, and the curve rises from 6:00 to 12:30 and falls afterwards.
- Fleet: 20 unique IDs. The same seed gives the same fleet, and a different seed gives a different one.
- Generator: 1000 generated messages all validate.
- Schema: temperature 500 is rejected, and an extra field is rejected.
- Publisher: an oversized payload is refused. The password never appears in captured logs.
- Runner: a 24-hour simulated run with FakeClock produces 20 times 5760 messages.
- Replay: the same seed gives a byte-identical JSONL file. Record its SHA-256 in the report.
- Integration (broker required, otherwise skipped): an anonymous subscriber receives nothing, and an authenticated subscriber receives messages.
- The generator contains no call to the system clock. Check this with a test that inspects the source.

## Deliverable
- Write `docs/baseline/sim_day_check.md` with peak power and daily energy per device for the 24-hour run. No site data.

## Checkpoints (stop and ask)
- If the daily power curve looks wrong for any device, stop and show the numbers before changing the curve.

## Done
- Update `docs/progress.md`. Commit in logical steps. Write the report, including the replay SHA-256.
