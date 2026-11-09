"""Input sanitization and output redaction security guard.

Purpose: Enforces content safety, canary detection, and secret redaction on all outgoing text.
Inputs: Free-form text, API responses, prompt arguments.
Outputs: Sanitized strings, redaction event counts.
"""
