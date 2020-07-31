PYTHON ?= python3.8

# Python Code Style
reformat:
	$(PYTHON) -m isort --atomic --line-length 120 .
	$(PYTHON) -m black -l 120 .
stylecheck:
	$(PYTHON) -m isort --atomic --check --line-length 120 .
	$(PYTHON) -m black --check -l 120 .
stylediff:
	$(PYTHON) -m isort --atomic --check --diff --line-length 120 .
	$(PYTHON) -m black --check --diff -l 120 .
