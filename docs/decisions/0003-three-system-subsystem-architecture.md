# 3. Three-System Subsystem Architecture and Command Polling

## Context
Solar plant telemetry architectures operate with clear operational boundaries:
1. Physical device fleet / Simulator representing on-site hardware.
2. Central Backend application responsible for monitoring, LLM multi-agent diagnosis, remediation policies, and audit logging.
3. Operator Frontend interface for human review and approval.

Furthermore, real inverters operate either by autonomous periodic telemetry streaming or by responding to explicit read/poll commands issued by the backend over MQTT or industrial bus protocols (e.g., Modbus RTU / Modbus TCP).

## Decision
1. Reorganize the project into 3 main root subsystems:
   - `simulator/`: Contains fleet generation, solar irradiance/thermal physical curves, telemetry synthesis, replay utilities, and command listener.
   - `backend/`: Contains common schemas, configuration, deterministic monitor, diagnosis/remediation LLM agents, LangGraph incident response workflow, human executor, and FastAPI backend.
   - `frontend/`: Dedicated client dashboard directory (scheduled for Phase 6).
2. Implement a `SimulatorCommandListener` in `simulator/listener.py` using an abstract `CommandTransport` protocol. Inverters listen on `fleet/inverter/{device_id}/command` for poll/read commands and publish telemetry in response, ready for future Modbus register adapters.
3. Enforce strict architectural isolation: `backend/` runtime code is prohibited from importing `simulator/` code directly.

## Consequences
- **Positive**: Strict system decoupling mirroring production OT/IT solar plant architectures.
- **Positive**: Simulator can run as an independent container or network service.
- **Positive**: Enables seamless future drop-in of Modbus RTU/TCP slave/server handlers without touching the physics simulator.
- **Negative / Neutral**: Shared contract models (`TelemetryMessage`) reside in `backend/common/schemas.py` and serve as the message schema definition.
