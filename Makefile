.PHONY: install lint type test security check run broker-users

PYTHON ?= python

install:
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	ruff check simulator backend tests
	ruff format --check simulator backend tests

type:
	mypy simulator backend tests

test:
	pytest tests -v

security:
	bandit -c pyproject.toml -r simulator backend
	pip-audit -r requirements.lock
	-gitleaks detect --no-git -v

check: lint type test security

run:
	@echo Starting IIR fleet simulation placeholder...
	@echo Run via: $(PYTHON) -m simulator.runner

broker-users:
	$(PYTHON) scripts/broker_users.py
