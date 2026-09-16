PYTHON ?= python
VENV := .venv

ifeq ($(OS),Windows_NT)
VENV_PYTHON := $(VENV)\Scripts\python.exe
VENV_PIP := $(VENV)\Scripts\pip.exe
else
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
endif

.PHONY: install run validate test serve clean

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt

run: install
	$(VENV_PYTHON) baseline_3sigma.py --data ./data --out ./predictions.csv

validate: run
	$(VENV_PYTHON) validate_submission.py --path ./predictions.csv

test: install
	$(VENV_PYTHON) -m pytest -v tests/

serve: install
	$(VENV_PYTHON) -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000

clean:
	rm -rf $(VENV)
	rm -f predictions.csv
