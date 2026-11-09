.PHONY: install lint type test security check run broker-users

PYTHON ?= python

install:
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	ruff check src tests
	ruff format --check src tests

type:
	mypy src tests

test:
	pytest tests -v

security:
	bandit -c pyproject.toml -r src
	pip-audit -r requirements.lock
	-gitleaks detect --no-git -v

check: lint type test security

run:
	@echo Starting IIR fleet simulation placeholder...
	@echo Run via: $(PYTHON) -m iir.simulator.runner

broker-users:
	$(PYTHON) scripts/broker_users.py
