.PHONY: build install help clean clean-test clean-pyc clean-build type_check lint test coverage check check_format fix_format format db-up db-down db-create-table db-seed run
.DEFAULT_GOAL := help

build: install lint type_check test ## install, lint, type check and test

install: ## install the package and dev dependencies
	uv sync

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/ coverage_html_report/
	rm -fr .pytest_cache

type_check: ## Check type hints with ty
	uv run ty check app scripts

lint: ## Check code with ruff
	uv run ruff check app scripts tests/


test: ## run tests quickly with the default Python
	uv run pytest tests/ -v


coverage: ## check code coverage quickly with the default Python
	uv run pytest --cov app --cov-report term-missing --cov-report html tests/

check: check_format lint type_check test ## run all checks without installing

check_format: ## check formatting with ruff
	$(info [*] Running ruff format checkers...)
	uv run ruff format --check app scripts tests/

fix_format: ## format code with ruff
	$(info [*] Running ruff format fixers...)
	uv run ruff format app scripts tests/

format: fix_format ## alias for fix_format

# Local DynamoDB Local run. The API itself runs on the host and talks to the
# container through DYNAMODB_ENDPOINT_URL.
LOCAL_DYNAMODB_URL = http://localhost:8000

db-up: ## start DynamoDB Local in the background
	docker compose up -d

db-down: ## stop DynamoDB Local and remove the container
	docker compose down

db-create-table: ## create the configured table on DynamoDB Local
	DYNAMODB_ENDPOINT_URL=$(LOCAL_DYNAMODB_URL) uv run python scripts/create_table.py

db-seed: ## write the sample items into the local table
	DYNAMODB_ENDPOINT_URL=$(LOCAL_DYNAMODB_URL) uv run python scripts/seed.py

run: ## serve the API on port 3000 against DynamoDB Local
	DYNAMODB_ENDPOINT_URL=$(LOCAL_DYNAMODB_URL) uv run uvicorn app.main:app --port 3000
