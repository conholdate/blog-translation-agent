.PHONY: test test-translation test-quality

# Run the full suite (paths come from pytest.ini)
test:
	python -m pytest -q

# Run only the Translation Pipeline tests (Steps 1-2)
test-translation:
	python -m pytest tools/translation_agent/tests/

# Run only the Quality Pipeline tests (Steps 3-4)
test-quality:
	python -m pytest tools/quality_agent/tests/
