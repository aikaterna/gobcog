PYTHON ?= python3.8

# Python Code Style
reformat:
	$(PYTHON) -m isort  --profile black.
	$(PYTHON) -m black .
stylecheck:
	$(PYTHON) -m isort --check  --profile black.
	$(PYTHON) -m black --check .
stylediff:
	$(PYTHON) -m isort --check --diff --profile black .
	$(PYTHON) -m black --check --diff .
