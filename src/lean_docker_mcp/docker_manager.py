"""Module for managing Docker containers to execute Lean4 code securely."""

import asyncio
import json
import logging
import os
import tempfile
from typing import Any, Dict, Optional

import docker

from .config import Configuration, load_config

# Set up logging
logger = logging.getLogger(__name__)


class DockerExecutionError(Exception):
    """Exception raised when Docker execution encounters an error."""

    pass


class DockerManager:
    """Manages Docker containers for executing Lean4 code."""

    def __init__(self, config: Optional[Configuration] = None):
        """Initialize the Docker manager with the given configuration."""
        self.config = config or load_config()
        self.client = docker.from_env()
        self.persistent_containers: Dict[str, str] = {}  # session_id -> container_id

    async def execute_transient(self, code: str) -> Dict[str, Any]:
        """Execute Lean4 code in a new container that doesn't persist state.

        Args:
            code: The Lean4 code to execute

        Returns:
            A dictionary containing the execution results
        """
        try:
            # Create temporary directory to mount inside the container
            with tempfile.TemporaryDirectory() as temp_dir:
                # Create Lean file with the code
                script_path = os.path.join(temp_dir, "Script.lean")
                output_path = os.path.join(temp_dir, "output.json")

                # Write the Lean code to a file
                with open(script_path, "w") as f:
                    f.write(code)

                # Run container with the script
                container = self.client.containers.run(
                    image=self.config.docker.image,
                    command=["lean", "-r", "/app/Script.lean"],
                    volumes={temp_dir: {"bind": "/app", "mode": "rw"}},
                    working_dir=self.config.docker.working_dir,
                    mem_limit=self.config.docker.memory_limit,
                    cpu_quota=int(self.config.docker.cpu_limit * 100000),  # Docker CPU quota in microseconds
                    network_disabled=self.config.docker.network_disabled,
                    read_only=self.config.docker.read_only,
                    remove=True,
                    detach=True,
                )

                # Wait for the container to finish or timeout
                try:
                    exit_code = await asyncio.wait_for(
                        self._wait_for_container(container.id),
                        timeout=self.config.docker.timeout,
                    )

                    # Get container logs
                    logs = container.logs().decode("utf-8")

                    # Check if the container exited with an error
                    if exit_code != 0:
                        raise DockerExecutionError(f"Container exited with code {exit_code}: {logs}")

                    return {
                        "output": logs,
                        "status": "success",
                        "exit_code": exit_code,
                    }

                except asyncio.TimeoutError:
                    # Force stop the container if it times out
                    try:
                        container.stop(timeout=1)
                    except Exception:
                        pass
                    raise DockerExecutionError(f"Execution timed out after {self.config.docker.timeout} seconds")

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
            A dictionary containing the execution results
        """
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

            # Escape single quotes for shell command
            safe_code = code.replace("'", "'\"'\"'")
            cmd = f"echo '{safe_code}' > /home/leanuser/project/{script_filename}"

            # Create the file inside the container
            script_create_cmd = container.exec_run(
                cmd=["sh", "-c", cmd],
                user="leanuser",
            )

            if script_create_cmd.exit_code != 0:
                raise DockerExecutionError(f"Failed to create script file: {script_create_cmd.output.decode('utf-8')}")

            # Execute the Lean code
            exec_result = container.exec_run(
                cmd=["lean", "-r", script_filename],
                workdir="/home/leanuser/project",
                user="leanuser",
            )

            # Capture the output
            output = exec_result.output.decode("utf-8")
            exit_code = exec_result.exit_code

            # Clean up the script file
            container.exec_run(
                cmd=["rm", f"/home/leanuser/project/{script_filename}"],
                user="leanuser",
            )

            return {
                "output": output,
                "status": "success" if exit_code == 0 else "error",
                "exit_code": exit_code,
            }

        except Exception as e:
            if isinstance(e, docker.errors.NotFound):
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
        except docker.errors.NotFound:
            # Container already gone, just remove the reference
            if session_id in self.persistent_containers:
                del self.persistent_containers[session_id]
            return {"status": "not_found", "message": f"Session {session_id} not found, may have already been cleaned up"}
        except Exception as e:
            return {"status": "error", "message": f"Error cleaning up session {session_id}: {str(e)}"}

    async def _wait_for_container(self, container_id: str) -> int:
        """Wait for a container to finish and return its exit code."""
        client = docker.APIClient()
        for _ in range(int(self.config.docker.timeout * 10)):  # Poll 10 times per second
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
            await asyncio.sleep(0.1)

        # If we got here, container is still running after timeout period
        return -1  # Indicate timeout 