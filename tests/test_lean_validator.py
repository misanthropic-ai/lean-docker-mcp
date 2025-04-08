"""Tests for the LeanCodeValidator class."""

import pytest
import re
from unittest.mock import patch

from lean_docker_mcp.config import Configuration, DockerConfig, LeanConfig
from lean_docker_mcp.docker_manager import LeanCodeValidator, LeanCompilationError


@pytest.fixture
def validator():
    """Create a LeanCodeValidator for testing."""
    config = Configuration(
        docker=DockerConfig(),
        lean=LeanConfig(
            allowed_imports=["Lean", "Init", "Std", "Mathlib"],
            blocked_imports=["System.IO.Process", "System.FilePath"],
        ),
    )
    return LeanCodeValidator(config)


class TestLeanCodeValidator:
    """Tests for the LeanCodeValidator class."""

    def test_safe_code(self, validator):
        """Test that safe Lean code passes validation."""
        safe_code = """
import Lean
import Std

def main : IO Unit :=
  IO.println "Hello, world!"
"""
        is_valid, error_message = validator.validate(safe_code)
        assert is_valid
        assert error_message is None

    def test_blocked_import(self, validator):
        """Test that code with blocked imports fails validation."""
        unsafe_code = """
import Lean
import System.IO.Process

def main : IO Unit :=
  IO.println "Trying to access process"
"""
        is_valid, error_message = validator.validate(unsafe_code)
        assert not is_valid
        assert "blocked for security reasons" in error_message

    def test_not_allowed_import(self, validator):
        """Test that code with imports not in allowed list fails validation."""
        unauthorized_code = """
import MyCustomPackage

def main : IO Unit :=
  IO.println "Using unauthorized package"
"""
        is_valid, error_message = validator.validate(unauthorized_code)
        assert not is_valid
        assert "not in the allowed list" in error_message

    def test_system_imports(self, validator):
        """Test that code with potentially unsafe System imports fails validation."""
        # The actual implementation will check if it's in the allowed list first
        # before checking if it's a potentially unsafe System import
        system_code = """
import Lean
import System.Command

def main : IO Unit :=
  IO.println "Trying to access system commands"
"""
        is_valid, error_message = validator.validate(system_code)
        assert not is_valid
        # Our validator should catch this as not in the allowed list
        assert "not in the allowed list" in error_message

    def test_io_operations(self, validator):
        """Test that code with IO operations fails validation."""
        io_code = """
import Lean

def main : IO Unit :=
  IO.FS.readFile "secretFile.txt"
"""
        is_valid, error_message = validator.validate(io_code)
        assert not is_valid
        assert "IO operation" in error_message


class TestLeanErrorParsing:
    """Tests for parsing Lean compiler errors."""

    def test_parse_type_mismatch(self, validator):
        """Test parsing type mismatch errors."""
        error_output = """
/app/Script.lean:5:12: error: type mismatch
  42
  ^
expected type
  IO Unit
but given type
  Nat
"""
        error = validator.parse_lean_error(error_output)
        assert error is not None
        assert error.error_type == "type_mismatch"
        assert error.line == 5
        assert error.column == 12
        assert "type mismatch" in error.message

    def test_parse_unknown_identifier(self, validator):
        """Test parsing unknown identifier errors."""
        error_output = """
/app/Script.lean:3:15: error: unknown identifier 'nonexistent'
  IO.println nonexistent
              ^
"""
        error = validator.parse_lean_error(error_output)
        assert error is not None
        assert error.error_type == "unknown_identifier"
        assert error.line == 3
        assert error.column == 15
        assert "unknown identifier" in error.message

    def test_parse_syntax_error(self, validator):
        """Test parsing syntax errors."""
        error_output = """
/app/Script.lean:2:10: error: syntax error
  def main :
           ^
expected ':=', got end of input
"""
        error = validator.parse_lean_error(error_output)
        assert error is not None
        assert error.error_type == "syntax_error"
        assert error.line == 2
        assert error.column == 10
        assert "syntax error" in error.message

    def test_parse_generic_error(self, validator):
        """Test parsing generic compilation errors."""
        # The current implementation checks for "error:" in the output
        error_output = "error: Failed to compile the file"
        error = validator.parse_lean_error(error_output)
        assert error is not None
        assert error.error_type == "compilation_error"
        assert "Failed to compile" in error.message

    def test_no_error(self, validator):
        """Test parsing output with no error."""
        output = "Hello, world!"
        error = validator.parse_lean_error(output)
        assert error is None

    def test_lean_compilation_error_to_dict(self):
        """Test conversion of LeanCompilationError to dict."""
        error = LeanCompilationError(
            message="Type mismatch error",
            error_type="type_mismatch",
            line=10,
            column=5
        )
        error_dict = error.to_dict()
        
        assert error_dict["error_type"] == "type_mismatch"
        assert error_dict["message"] == "Type mismatch error"
        assert error_dict["line"] == 10
        assert error_dict["column"] == 5