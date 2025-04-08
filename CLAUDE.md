# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands
- Install dev dependencies: `uv pip install -e ".[dev]"`
- Run all tests: `pytest`
- Run specific test file: `pytest tests/unit/test_config.py`
- Run specific test function: `pytest tests/unit/test_config.py::test_default_config`
- Run tests with coverage: `pytest --cov=src/lean_docker_mcp`
- Install pre-commit hooks: `pre-commit install`

## Code Style Guidelines
- Line length: 160 characters (Black configured)
- Python version: 3.11+ required
- Type hints required for all functions/methods (disallow_untyped_defs=True)
- Use absolute imports, isort with black profile
- Black formatting: configured for py311 target
- Exception handling: Always log exceptions with context, use custom exception classes
- Error messages: Include detailed context for debugging
- Naming: snake_case for functions/variables, PascalCase for classes
- Docstrings: Required for all modules, classes, methods (include Args, Returns)
- Testing: Use pytest, maintain >80% coverage

## Docker & MCP Guidelines
- Never expose container to external networks
- Always validate Lean code before execution
- Document all configuration options clearly
- Implement proper resource limits and timeouts
- Properly handle Lean-specific errors and compile messages

## TODO List
1. Docker Manager Fixes:
   - Fix `timeout` parameter usage in `docker_manager.py` - use docker.timeout
   - Correct properties like `cpu_count` to `cpu_limit` and `network` to `network_disabled`
   
2. Lean Code Validation:
   - Implement validation for Lean imports based on allowed_imports/blocked_imports
   - Add regex pattern matching for detecting unsafe imports
   - Create a LeanCodeValidator class to handle validation

3. Dockerfile Improvements:
   - Consider pre-installing Mathlib for better performance
   - Add script to build and tag the Docker image

4. Error Handling:
   - Improve parsing of Lean-specific error messages
   - Create error classification for common Lean errors
   - Add LeanCompilationError exception type

5. Testing:
   - Update test fixtures to use valid Lean 4 syntax
   - Create specific tests for Lean 4 import validation
   - Add integration tests with real Lean 4 code samples

6. Documentation:
   - Update examples to use proper Lean 4 syntax
   - Document Lean 4 specific error messages and codes