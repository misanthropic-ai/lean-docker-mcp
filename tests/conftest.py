"""Pytest configuration and fixtures for lean-docker-mcp tests."""

import os
import tempfile
from typing import Dict, Generator, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sys
import pytest_asyncio

from lean_docker_mcp.config import Configuration, DockerConfig, LeanConfig
from lean_docker_mcp.docker_manager import DockerManager

# Add the src directory to the path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import after path is set
from lean_docker_mcp.config import Configuration
from lean_docker_mcp.docker_manager import DockerManager


@pytest.fixture
def mock_container():
    """Create a mock Docker container."""
    container = MagicMock()
    container.id = "test-container-id"
    container.name = "test-container-name"
    container.wait = MagicMock(return_value={"StatusCode": 0})
    container.logs = MagicMock(return_value=b"Hello, Lean4!\n")
    container.stop = MagicMock()
    container.remove = MagicMock()
    container.exec_run = MagicMock(return_value=(0, b"Hello from persistent container!\n"))
    return container


@pytest.fixture
def mock_client(mock_container):
    """Create a mock Docker client."""
    client = MagicMock()
    client.containers = MagicMock()
    client.containers.create = MagicMock(return_value=mock_container)
    client.containers.get = MagicMock(return_value=mock_container)
    client.containers.list = MagicMock(return_value=[])  # Initially no containers
    return client


@pytest_asyncio.fixture
async def docker_manager(mock_client):
    """Create a DockerManager with a mocked Docker client."""
    with patch("lean_docker_mcp.docker_manager.docker") as mock_docker:
        mock_docker.from_env.return_value = mock_client
        # Create a simple configuration
        docker_config = MagicMock()
        docker_config.image = "leanprover/lean:latest"
        docker_config.container_name_prefix = "lean-docker-mcp"
        
        lean_config = MagicMock()
        
        config = MagicMock()
        config.docker = docker_config
        config.lean = lean_config
        
        # Create a DockerManager instance with the mocked configuration
        manager = DockerManager(config)
        yield manager


@pytest.fixture
def mock_docker_client() -> MagicMock:
    """Mock docker client for testing."""
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_client.containers.run.return_value = mock_container
    mock_client.containers.get.return_value = mock_container
    return mock_client


@pytest.fixture
def mock_docker_manager():
    """Return a mock docker manager."""
    mock = MagicMock()
    
    # Configure execute_transient to return a success response
    mock.execute_transient = AsyncMock(return_value={
        "status": "success",
        "output": "Hello, Lean4!\n"
    })
    
    # Configure execute_persistent to return a success response
    mock.execute_persistent = AsyncMock(return_value={
        "status": "success",
        "output": "Hello, Lean4!\n"
    })
    
    # Configure cleanup_session to return a success response
    mock.cleanup_session = AsyncMock(return_value={
        "status": "success"
    })
    
    return mock


@pytest.fixture
def temp_config_file() -> Generator[str, None, None]:
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".yaml", delete=False) as f:
        f.write("""
docker:
  image: lean-docker-mcp:latest
  working_dir: /home/leanuser/project
  memory_limit: 256m
  cpu_limit: 0.5
  timeout: 30
  network_disabled: true
  read_only: false

lean:
  allowed_imports:
    - Lean
    - Init
    - Std
  blocked_imports:
    - System.IO.Process
    - System.FilePath
""")
        f.flush()
        file_path = f.name

    yield file_path
    os.unlink(file_path)


@pytest.fixture
def test_config() -> Configuration:
    """Create a test configuration."""
    docker_config = DockerConfig(
        image="lean-docker-mcp:latest",
        working_dir="/home/leanuser/project",
        memory_limit="256m",
        cpu_limit=0.5,
        timeout=30,
        network_disabled=True,
        read_only=False,
    )
    
    lean_config = LeanConfig(
        allowed_imports=["Lean", "Init", "Std"],
        blocked_imports=["System.IO.Process", "System.FilePath"],
    )
    
    return Configuration(docker=docker_config, lean=lean_config)
