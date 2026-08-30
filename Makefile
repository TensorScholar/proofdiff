.PHONY: test coverage schemas benchmark dist smoke release-check

test:
	PYTHONPATH=src python -m pytest -q

coverage:
	PYTHONPATH=src coverage run --branch -m pytest -q
	PYTHONPATH=src coverage report -m

schemas:
	PYTHONPATH=src python scripts/check_schemas.py

benchmark:
	PYTHONPATH=src python benchmarks/run_benchmark.py

dist:
	PYTHONPATH=src python scripts/build_dist.py

smoke: dist
	PYTHONPATH=src python scripts/smoke_install.py

release-check:
	PYTHONPATH=src python scripts/check_release.py
