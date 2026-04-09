VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: venv install run lint typecheck format test test-e2e check clean

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install -e ".[dev]"

run: install
	$(VENV)/bin/juris $(ARGS)

lint:
	$(PYTHON) -m ruff check src/ tests/
	$(PYTHON) -m ruff format --check src/ tests/

typecheck:
	$(PYTHON) -m mypy src/

format:
	$(PYTHON) -m ruff format src/ tests/

test:
	$(PYTHON) -m pytest tests/ -v --ignore=tests/test_e2e.py

test-e2e:
	$(PYTHON) -m pytest tests/ -v -m e2e

check: lint typecheck test

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache
