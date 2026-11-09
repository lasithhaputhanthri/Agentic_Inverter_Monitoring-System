# IoT Incident Response (Simulated Fleet)

A multi-agent incident response system for a **simulated** fleet of 20 solar inverters communicating over MQTT.

## Security Notice
- No real hardware is controlled anywhere in this project.
- SEC-51: In production configurations, MQTT connections must use TLS (port 8883). Local development uses plain localhost (port 1883).
- Secrets are loaded exclusively from environment variables. Never commit credentials to source control.

## Setup & Commands
See `Makefile` and `.agents/workflows/` for operational procedures.
