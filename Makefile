.PHONY: install test refresh fmt

PYTHON ?= python3
VENV := .venv

install:
	$(PYTHON) -m venv $(VENV)
	. $(VENV)/bin/activate && pip install -e ".[dev]"
	. $(VENV)/bin/activate && scrapling install

test:
	. $(VENV)/bin/activate && pytest -q

fmt:
	. $(VENV)/bin/activate && ruff check --fix src tests && ruff format src tests

# Quarterly refresh. Usage: make refresh SPREADSHEET=TS_Price_List_T2_April_2026.xlsx
refresh:
	@test -n "$(SPREADSHEET)" || (echo "SPREADSHEET=path/to/file.xlsx required" && exit 1)
	. $(VENV)/bin/activate && showroom-refresh --spreadsheet "$(SPREADSHEET)"
