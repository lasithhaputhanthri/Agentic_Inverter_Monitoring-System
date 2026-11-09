"""Rate limiting, token budgeting, and concurrency load control.

Purpose: Enforces request limits, LLM token quotas, circuit breakers, and alert cooldowns.
Inputs: Incoming requests, LLM token counts.
Outputs: Rate-limit decisions, quota tracking, load shed signals.
"""
