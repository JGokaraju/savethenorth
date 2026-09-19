PY ?= python

.PHONY: setup prep dev test demo inventory
setup:
	$(PY) tasks.py setup
prep:
	$(PY) tasks.py prep
dev:
	$(PY) tasks.py dev
test:
	$(PY) tasks.py test
demo:
	$(PY) tasks.py demo
inventory:
	$(PY) tasks.py inventory
