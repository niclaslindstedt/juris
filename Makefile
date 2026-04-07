VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: venv install lint typecheck format test test-e2e clean

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install -e ".[dev]"

lint:
	$(PYTHON) -m ruff check src/

typecheck:
	$(PYTHON) -m mypy src/

format:
	$(PYTHON) -m ruff format --check src/

test:
	$(PYTHON) -m pytest tests/ -v --ignore=tests/test_e2e.py

test-e2e:
	$(PYTHON) -m pytest tests/ -v -m e2e

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache
