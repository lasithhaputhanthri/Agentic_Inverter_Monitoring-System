# Security Policy

## Reporting a Vulnerability

We take the security of this project seriously. Because this project simulates industrial solar inverter fleet telemetry and incident response, safe operation and robust boundary controls are fundamental design pillars.

If you discover a security vulnerability or security boundary bypass, please report it privately:

- **Email**: `security@inverter-ai-project.local` (or create a private GitHub Security Advisory)
- **Response Time**: We acknowledge receipt of vulnerability reports within 48 hours and provide remediation updates within 7 business days.

Please include:
1. Description of the vulnerability and affected component (`simulator`, `backend`, `api`, `workflow`).
2. Exact steps or script to reproduce the vulnerability.
3. Impact assessment (e.g., unauthorized executor action, LLM injection breakout, credential disclosure).

**Please do not disclose security issues publicly until a coordinated patch and disclosure plan has been established.**

## Security Scope & Hard Boundaries

This project enforces strict security boundaries as documented in `docs/security.md`:
- **No Real Hardware**: All telemetry, inverters, and actuators are simulated. No real hardware is ever connected or controlled.
- **Strict Role-Based Access Control**: API keys are hashed with salt and validated with constant-time equality checks.
- **Mandatory Human Approval**: No remediation action is ever executed without explicit operator approval.
- **Prompt Injection Defense**: All untrusted telemetry and incident context are wrapped in XML delimiters and treated as passive data.
