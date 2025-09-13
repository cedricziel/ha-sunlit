.PHONY: help format lint check test test-cov setup clean

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

format: ## Format code with ruff and isort
	@echo "Formatting with ruff..."
	@ruff format custom_components/sunlit/
	@echo "Sorting imports with isort..."
	@isort custom_components/sunlit/
	@echo "Fixing with ruff..."
	@ruff check --fix custom_components/sunlit/
	@echo "✓ Code formatted successfully"

lint: ## Run all linters without making changes
	@echo "Running ruff check..."
	@ruff check custom_components/sunlit/
	@echo "Running ruff format check..."
	@ruff format --check custom_components/sunlit/
	@echo "Running isort check..."
	@isort --check-only custom_components/sunlit/
	@echo "✓ All checks passed"

check: lint ## Alias for lint

test: ## Run tests with pytest
	@echo "Running tests..."
	@pytest tests/ -v --asyncio-mode=auto
	@echo "✓ Tests completed"

test-cov: ## Run tests with coverage report
	@echo "Running tests with coverage..."
	@pytest tests/ -v --asyncio-mode=auto --cov=custom_components.sunlit --cov-report=term-missing --cov-report=xml --cov-report=html --timeout=30
	@echo "✓ Coverage report generated (see htmlcov/index.html)"

setup: ## Install development dependencies
	@echo "Installing dependencies..."
	@python3 -m pip install --requirement requirements.txt
	@echo "✓ Dependencies installed"
	@python3 -m pip install --requirement requirements-dev.txt
	@echo "✓ Development dependencies installed"

clean: ## Clean up cache and temporary files
	@echo "Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type f -name ".coverage" -delete
	@rm -rf .ruff_cache
	@rm -rf .pytest_cache
	@rm -rf htmlcov
	@echo "✓ Cleaned up cache files"
