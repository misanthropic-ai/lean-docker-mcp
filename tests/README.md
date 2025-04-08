# Lean Docker MCP Tests

This directory contains tests for the Lean Docker MCP project. The tests are organized as follows:

## Test Structure

- `unit/`: Unit tests for individual components
  - `test_config.py`: Tests for the configuration module
  - `test_docker_manager.py`: Tests for the Docker manager module
  - `test_main.py`: Tests for the CLI main module
  - `test_server.py`: Tests for the JSON-RPC server module

- `integration/`: Integration tests for the full system
  - `test_integration.py`: Tests for the complete workflow

## Running Tests

To run the tests, use pytest:

```bash
# Run all tests
pytest

# Run specific tests
pytest tests/unit/test_config.py
pytest tests/integration/

# Run with coverage
pytest --cov=lean_docker_mcp
```

## Test Dependencies

The tests require the following dependencies:
- pytest
- pytest-asyncio
- pytest-cov (for coverage)

These can be installed via:

```bash
pip install pytest pytest-asyncio pytest-cov
``` 