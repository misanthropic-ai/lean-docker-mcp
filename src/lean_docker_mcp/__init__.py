"""Lean Docker MCP package for running Lean4 code in isolated Docker containers.

This package provides a server that accepts Lean4 code execution requests and runs
them in isolated Docker containers for security.
"""

import asyncio
import logging
import os
import subprocess
from typing import List, Optional

from . import config, docker_manager, server
from .config import load_config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lean-docker-mcp")

# Package metadata
__version__ = "0.1.0"
__title__ = "lean-docker-mcp"
__description__ = "A server for executing Lean code in isolated Docker containers"
__author__ = "Artivus Team"
__license__ = "MIT"


def check_docker_image_exists(image_name: str) -> bool:
    """Check if a Docker image exists locally."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image_name],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error checking Docker image: {e}")
        return False


def get_docker_images(base_name: str) -> List[str]:
    """Get list of Docker images with the given base name."""
    try:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}", base_name],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return []
    except Exception as e:
        logger.error(f"Error listing Docker images: {e}")
        return []


def ensure_docker_image(image_name: Optional[str] = None) -> None:
    """Ensure the Docker image exists with the correct version, building it if necessary."""
    if image_name is None:
        # Default image name if none is provided
        image_name = "lean-docker-mcp:latest"
    
    # Check if the image exists
    if not check_docker_image_exists(image_name):
        logger.info(f"Docker image {image_name} not found. Please build it manually using the provided Dockerfile.")
        logger.info("You can build it with: docker build -t lean-docker-mcp:latest -f /path/to/Dockerfile .")
    else:
        logger.info(f"Docker image {image_name} already exists.")


def main() -> None:
    """Main entry point for the package."""
    try:
        # Ensure the Docker image exists before starting the server
        ensure_docker_image()

        # Run the server
        asyncio.run(server.main())
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
        raise


# Expose important items at package level
__all__ = [
    "main", 
    "server", 
    "config", 
    "docker_manager", 
    "__version__",
    "__title__",
    "__description__",
    "__author__",
    "__license__",
] 