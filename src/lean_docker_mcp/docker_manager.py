"""Module for managing Docker containers to execute Lean4 code securely."""

import asyncio
import json
import logging
import os
import re
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import docker
from docker.errors import NotFound

from .config import Configuration, load_config

# Set up logging
logger = logging.getLogger(__name__)


class DockerExecutionError(Exception):
    """Exception raised when Docker execution encounters an error."""

    pass


class LeanValidationError(Exception):
    """Exception raised when Lean code validation fails."""

    pass


class LeanCompilationError(Exception):
    """Exception raised when Lean code fails to compile.
    
    This provides more structured information about Lean-specific errors.
    """
    
    def __init__(self, message: str, error_type: str = "unknown", line: Optional[int] = None, column: Optional[int] = None):
        """Initialize the error.
        
        Args:
            message: The error message
            error_type: The type of Lean error (e.g., "type_error", "syntax_error")
            line: Optional line number where the error occurred
            column: Optional column number where the error occurred
        """
        self.error_type = error_type
        self.line = line
        self.column = column
        self.message = message
        super().__init__(message)
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert the error to a dictionary for JSON serialization."""
        return {
            "error_type": self.error_type,
            "message": self.message,
            "line": self.line,
            "column": self.column,
        }


class LeanCodeValidator:
    """Validates Lean code for security and safety."""

    def __init__(self, config: Configuration):
        """Initialize the validator with configuration.
        
        Args:
            config: The configuration for validation
        """
        self.config = config
        self._compile_regex_patterns()

    def _compile_regex_patterns(self) -> None:
        """Compile regex patterns for detecting unsafe imports."""
        # Build regex patterns for allowed and blocked imports
        allowed_patterns = [re.escape(imp) for imp in self.config.lean.allowed_imports]
        blocked_patterns = [re.escape(imp) for imp in self.config.lean.blocked_imports]
        
        # Also look for common System imports that might be unsafe
        self.system_import_pattern = re.compile(r'import\s+System\.(?!Data|Option|Environment|String|Nat|Int|UInt)')
        
        # Pattern for finding all imports
        self.import_pattern = re.compile(r'import\s+([A-Za-z0-9_.]+)')
        
        # Pattern for finding IO operations
        self.io_pattern = re.compile(r'IO\.(FS|Process|FileSystem|Handle|Socket|Terminal)')

    def validate(self, code: str) -> Tuple[bool, Optional[str]]:
        """Validate Lean code for safety.
        
        Args:
            code: The Lean code to validate
            
        Returns:
            A tuple of (is_valid, error_message)
        """
        # Find all imports in the code
        imports = self.import_pattern.findall(code)
        
        # Check for blocked imports
        for import_name in imports:
            if import_name in self.config.lean.blocked_imports:
                return False, f"Import '{import_name}' is blocked for security reasons"
                
        # Check if all imports are in the allowed list
        if self.config.lean.allowed_imports:
            for import_name in imports:
                if import_name not in self.config.lean.allowed_imports:
                    return False, f"Import '{import_name}' is not in the allowed list"
        
        # Check for potentially unsafe System imports
        if self.system_import_pattern.search(code):
            return False, "Potentially unsafe System import detected"
            
        # Check for IO operations
        if self.io_pattern.search(code):
            return False, "Potentially unsafe IO operation detected"
            
        return True, None
        
    def parse_lean_error(self, output: str) -> Optional[LeanCompilationError]:
        """Parse Lean compilation error output and convert to structured error.
        
        Args:
            output: The error output from Lean
            
        Returns:
            A LeanCompilationError or None if no error could be parsed
        """
        if not output or "error:" not in output.lower():
            return None
            
        # Common Lean 4 error patterns
        # Example: file.lean:10:5: error: unknown identifier 'foo'
        error_pattern = re.compile(r'.*:(\d+):(\d+):\s+error:\s+(.*)')
        
        for line in output.splitlines():
            match = error_pattern.match(line)
            if match:
                line_num = int(match.group(1))
                col_num = int(match.group(2))
                message = match.group(3).strip()
                
                # Determine error type based on message content
                error_type = "unknown"
                if "unknown identifier" in message:
                    error_type = "unknown_identifier"
                elif "type mismatch" in message:
                    error_type = "type_mismatch"
                elif "syntax error" in message:
                    error_type = "syntax_error"
                elif "expected type" in message:
                    error_type = "type_error"
                
                return LeanCompilationError(
                    message=message,
                    error_type=error_type,
                    line=line_num,
                    column=col_num
                )
                
        # If we couldn't parse a specific error, return a generic one
        return LeanCompilationError(
            message="Lean compilation error: " + output.split("\n")[0],
            error_type="compilation_error"
        )


class DockerManager:
    """Manages Docker containers for executing Lean4 code."""

    def __init__(self, config: Optional[Configuration] = None):
        """Initialize the Docker manager with the given configuration."""
        self.config = config or load_config()
        self.client = docker.from_env()
        self.persistent_containers: Dict[str, str] = {}  # session_id -> container_id
        self.validator = LeanCodeValidator(self.config)

    async def execute_transient(self, code: str) -> Dict[str, Any]:
        """Execute Lean4 code in a new container that doesn't persist state.

        Args:
            code: The Lean4 code to execute

        Returns:
            A dictionary containing the execution results with stdout, error information and status
        """
        try:
            # Validate the code first
            is_valid, error_message = self.validator.validate(code)
            if not is_valid:
                return {
                    "stdout": "",
                    "error": f"Validation error: {error_message}",
                    "error_type": "validation_error",
                    "status": "error",
                }
                
            # Create temporary directory to mount inside the container
            with tempfile.TemporaryDirectory() as temp_dir:
                # Create Lean file with the code
                script_path = os.path.join(temp_dir, "Script.lean")
                
                # Create a wrapper script to capture output and errors
                lean_runner_path = os.path.join(temp_dir, "run_lean.sh")
                
                # Write the Lean code to a file
                with open(script_path, "w") as f:
                    f.write(code)
                
                # Create a wrapper script to run Lean and capture different streams
                with open(lean_runner_path, "w") as f:
                    f.write(f"""#!/bin/bash
# Wrapper script to execute Lean and capture output streams
lean_output=$(lean -r /app/Script.lean 2>&1)
exit_code=$?

# Write structured result with clear markers for parsing
echo "---LEAN_OUTPUT_START---"
echo "$lean_output"
echo "---LEAN_OUTPUT_END---"
echo "---LEAN_EXIT_CODE_START---"
echo "$exit_code"
echo "---LEAN_EXIT_CODE_END---"
exit $exit_code
""")
                
                # Make the wrapper script executable
                os.chmod(lean_runner_path, 0o755)

                # Run container synchronously with the script
                container_output = self.client.containers.run(
                    image=self.config.docker.image,
                    command=["timeout", str(self.config.docker.timeout), "/app/run_lean.sh"],
                    volumes={temp_dir: {"bind": "/app", "mode": "rw"}},
                    working_dir="/app",  # Execute in the mounted volume
                    mem_limit=self.config.docker.memory_limit,
                    cpu_quota=int(self.config.docker.cpu_limit * 100000),
                    network_disabled=self.config.docker.network_disabled,
                    remove=True,
                    detach=False,  # Run synchronously
                )

                # Decode the output
                output = container_output.decode("utf-8")
                
                # Parse the structured output
                lean_output = ""
                exit_code = -1
                
                # Extract the Lean output
                output_start = output.find("---LEAN_OUTPUT_START---")
                output_end = output.find("---LEAN_OUTPUT_END---")
                if output_start >= 0 and output_end >= 0:
                    lean_output = output[output_start + len("---LEAN_OUTPUT_START---"):output_end].strip()
                
                # Extract the exit code
                exit_code_start = output.find("---LEAN_EXIT_CODE_START---")
                exit_code_end = output.find("---LEAN_EXIT_CODE_END---")
                if exit_code_start >= 0 and exit_code_end >= 0:
                    exit_code_str = output[exit_code_start + len("---LEAN_EXIT_CODE_START---"):exit_code_end].strip()
                    try:
                        exit_code = int(exit_code_str)
                    except ValueError:
                        exit_code = -1

                # Check for Lean-specific errors and parse them if present
                is_success = exit_code == 0 and "error:" not in lean_output.lower()
                
                result = {
                    "stdout": lean_output,
                    "exit_code": exit_code,
                    "status": "success" if is_success else "error",
                }
                
                # If there was an error, add more detailed error information
                if not is_success:
                    lean_error = self.validator.parse_lean_error(lean_output)
                    if lean_error:
                        result["error"] = lean_error.message
                        result["error_info"] = lean_error.to_dict()
                    else:
                        result["error"] = "Lean execution error" if exit_code != 0 else "Unknown error in Lean output"
                
                return result

        except Exception as e:
            if not isinstance(e, DockerExecutionError):
                raise DockerExecutionError(f"Error executing code in Docker: {str(e)}")
            raise

    async def execute_persistent(self, session_id: str, code: str) -> Dict[str, Any]:
        """Execute Lean4 code in a persistent container that retains state between calls.

        Args:
            session_id: A unique identifier for the session
            code: The Lean4 code to execute

        Returns:
            A dictionary containing the execution results with stdout, error information and status
        """
        # Validate the code first
        is_valid, error_message = self.validator.validate(code)
        if not is_valid:
            return {
                "stdout": "",
                "error": f"Validation error: {error_message}",
                "error_type": "validation_error",
                "status": "error",
            }
            
        container_id = self.persistent_containers.get(session_id)

        # Create a new container if it doesn't exist
        if not container_id:
            # Store the desired network state to track later
            should_disable_network = self.config.docker.network_disabled

            # Always create with network initially enabled, we can disable it after setup if needed
            container = self.client.containers.run(
                image=self.config.docker.image,
                command=[
                    "sh",
                    "-c",
                    "cd /home/leanuser/project && sleep 86400",
                ],  # Run for 24 hours
                working_dir=self.config.docker.working_dir,
                mem_limit=self.config.docker.memory_limit,
                cpu_quota=int(self.config.docker.cpu_limit * 100000),
                network_disabled=False,  # Initialize with network enabled for setup
                read_only=False,  # Need to be writable for persistent sessions
                detach=True,
                labels={
                    "lean_docker_mcp.network_disabled": str(should_disable_network),
                    "lean_docker_mcp.session_id": session_id,
                },
            )
            container_id = container.id
            self.persistent_containers[session_id] = container_id

            # After container is created and set up, disable network if that was the config setting
            if should_disable_network:
                try:
                    # Refresh the container object to get updated network info
                    container = self.client.containers.get(container_id)

                    # Disconnect from all networks if network should be disabled
                    for network_name in container.attrs.get("NetworkSettings", {}).get("Networks", {}):
                        try:
                            self.client.networks.get(network_name).disconnect(container)
                            logger.info(f"Disabled network {network_name} for container {container_id}")
                        except Exception as e:
                            logger.warning(f"Could not disable network {network_name}: {e}")
                except Exception as e:
                    logger.warning(f"Could not apply network settings to container {container_id}: {e}")

        # Execute the code in the container
        try:
            container = self.client.containers.get(container_id)

            # Create a temporary file with the code
            exec_id = os.urandom(8).hex()
            script_filename = f"Script_{exec_id}.lean"
            wrapper_filename = f"run_lean_{exec_id}.sh"

            # Escape single quotes for shell command
            safe_code = code.replace("'", "'\"'\"'")
            
            # Create the Lean file
            cmd = f"echo '{safe_code}' > /home/leanuser/project/{script_filename}"
            script_create_cmd = container.exec_run(
                cmd=["sh", "-c", cmd],
                user="leanuser",
            )

            if script_create_cmd.exit_code != 0:
                raise DockerExecutionError(f"Failed to create script file: {script_create_cmd.output.decode('utf-8')}")

            # Create a wrapper script to capture output
            wrapper_script = f"""#!/bin/bash
# Wrapper script to execute Lean and capture output streams
lean_output=$(lean -r /home/leanuser/project/{script_filename} 2>&1)
exit_code=$?

# Write structured result with clear markers for parsing
echo "---LEAN_OUTPUT_START---"
echo "$lean_output"
echo "---LEAN_OUTPUT_END---"
echo "---LEAN_EXIT_CODE_START---"
echo "$exit_code"
echo "---LEAN_EXIT_CODE_END---"

# Clean up the script file
rm -f /home/leanuser/project/{script_filename}

exit $exit_code
"""
            # Escape single quotes for shell command
            safe_wrapper = wrapper_script.replace("'", "'\"'\"'")
            cmd = f"echo '{safe_wrapper}' > /home/leanuser/project/{wrapper_filename} && chmod +x /home/leanuser/project/{wrapper_filename}"
            
            wrapper_create_cmd = container.exec_run(
                cmd=["sh", "-c", cmd],
                user="leanuser",
            )

            if wrapper_create_cmd.exit_code != 0:
                raise DockerExecutionError(f"Failed to create wrapper script: {wrapper_create_cmd.output.decode('utf-8')}")

            # Execute the wrapper script
            exec_result = container.exec_run(
                cmd=[f"/home/leanuser/project/{wrapper_filename}"],
                workdir="/home/leanuser/project",
                user="leanuser",
            )

            # Capture the output
            output = exec_result.output.decode("utf-8")
            exit_code = exec_result.exit_code

            # Clean up the wrapper script
            container.exec_run(
                cmd=["rm", f"/home/leanuser/project/{wrapper_filename}"],
                user="leanuser",
            )
            
            # Parse the structured output
            lean_output = ""
            parsed_exit_code = exit_code  # Default to the exit code from exec_run
            
            # Extract the Lean output
            output_start = output.find("---LEAN_OUTPUT_START---")
            output_end = output.find("---LEAN_OUTPUT_END---")
            if output_start >= 0 and output_end >= 0:
                lean_output = output[output_start + len("---LEAN_OUTPUT_START---"):output_end].strip()
            
            # Extract the exit code from the output
            exit_code_start = output.find("---LEAN_EXIT_CODE_START---")
            exit_code_end = output.find("---LEAN_EXIT_CODE_END---")
            if exit_code_start >= 0 and exit_code_end >= 0:
                exit_code_str = output[exit_code_start + len("---LEAN_EXIT_CODE_START---"):exit_code_end].strip()
                try:
                    parsed_exit_code = int(exit_code_str)
                except ValueError:
                    parsed_exit_code = exit_code  # Fall back to the original exit code
                    
            # Check for Lean-specific errors and parse them if present
            is_success = parsed_exit_code == 0 and "error:" not in lean_output.lower()
            
            result = {
                "stdout": lean_output,
                "exit_code": parsed_exit_code,
                "status": "success" if is_success else "error",
                "session_id": session_id,  # Include the session ID in the response
            }
            
            # If there was an error, add more detailed error information
            if not is_success:
                lean_error = self.validator.parse_lean_error(lean_output)
                if lean_error:
                    result["error"] = lean_error.message
                    result["error_info"] = lean_error.to_dict()
                else:
                    result["error"] = "Lean execution error" if parsed_exit_code != 0 else "Unknown error in Lean output"
            
            return result

        except Exception as e:
            if isinstance(e, NotFound):
                # Container no longer exists, remove from tracked containers
                if session_id in self.persistent_containers:
                    del self.persistent_containers[session_id]
                raise DockerExecutionError(f"Session {session_id} has expired or was deleted")
            else:
                raise DockerExecutionError(f"Error executing Lean code: {str(e)}")

    async def cleanup_session(self, session_id: str) -> Dict[str, Any]:
        """Clean up a persistent session.

        Args:
            session_id: The session ID to clean up

        Returns:
            A dictionary indicating success or failure
        """
        container_id = self.persistent_containers.get(session_id)
        if not container_id:
            return {"status": "not_found", "message": f"No session found with ID {session_id}"}

        try:
            container = self.client.containers.get(container_id)
            container.stop()
            container.remove()
            del self.persistent_containers[session_id]
            return {"status": "success", "message": f"Session {session_id} cleaned up successfully"}
        except NotFound:
            # Container already gone, just remove the reference
            if session_id in self.persistent_containers:
                del self.persistent_containers[session_id]
            return {"status": "not_found", "message": f"Session {session_id} not found, may have already been cleaned up"}
        except Exception as e:
            return {"status": "error", "message": f"Error cleaning up session {session_id}: {str(e)}"}

    async def _wait_for_container(self, container_id: str) -> int:
        """Wait for a container to finish and return its exit code."""
        client = docker.APIClient()
        poll_interval = 0.1  # 100ms between polls
        max_polls = int(self.config.docker.timeout / poll_interval)
        
        for _ in range(max_polls):  # Poll 10 times per second
            try:
                container_info = client.inspect_container(container_id)
                if not container_info["State"]["Running"]:
                    return container_info["State"]["ExitCode"]
            except docker.errors.NotFound:
                # Container removed, assume success
                return 0
            except Exception as e:
                logger.warning(f"Error checking container state: {e}")
                # Continue waiting despite the error
            await asyncio.sleep(poll_interval)

        # If we got here, container is still running after timeout period
        logger.warning(f"Container {container_id} timed out after {self.config.docker.timeout} seconds")
        return -1  # Indicate timeout