"""Configuration module for Lean Docker MCP."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)

# Default configuration directory
DEFAULT_CONFIG_DIR = os.path.expanduser("~/.lean-docker-mcp")
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_CONFIG_DIR, "config.yaml")


@dataclass
class DockerConfig:
    """Docker container configuration."""

    image: str = "lean-docker-mcp:latest"
    working_dir: str = "/home/leanuser/project"
    memory_limit: str = "256m"
    cpu_limit: float = 0.5
    timeout: int = 30
    network_disabled: bool = True
    read_only: bool = False


@dataclass
class LeanConfig:
    """Lean4 specific configuration."""

    allowed_imports: List[str] = field(default_factory=lambda: ["Lean", "Init", "Std", "Mathlib"])
    blocked_imports: List[str] = field(default_factory=lambda: ["System.IO.Process", "System.FilePath"])


@dataclass
class Configuration:
    """Main configuration class."""

    docker: DockerConfig
    lean: LeanConfig

    @classmethod
    def from_dict(cls, config_dict: Dict) -> "Configuration":
        """Create a Configuration object from a dictionary."""
        docker_config = DockerConfig(**config_dict.get("docker", {}))
        lean_config = LeanConfig(**config_dict.get("lean", {}))
        
        return cls(
            docker=docker_config,
            lean=lean_config,
        )


def load_config(config_path: Optional[str] = None) -> Configuration:
    """Load configuration from a YAML file.

    Args:
        config_path: Path to the configuration file. If None, the default path is used.

    Returns:
        A Configuration object with the loaded configuration.
    """
    # If no config path is provided, use the default
    if config_path is None:
        config_path = os.environ.get("LEAN_DOCKER_MCP_CONFIG", DEFAULT_CONFIG_PATH)

    # Load configuration from file if it exists
    config_dict = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config_dict = yaml.safe_load(f) or {}
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.warning(f"Error loading configuration from {config_path}: {e}")
            logger.warning("Using default configuration")
    else:
        logger.info(f"Configuration file {config_path} not found. Using default configuration.")
        # Try to load the bundled default configuration
        default_config_file = os.path.join(os.path.dirname(__file__), "default_config.yaml")
        if os.path.exists(default_config_file):
            try:
                with open(default_config_file, "r") as f:
                    config_dict = yaml.safe_load(f) or {}
                logger.info(f"Loaded default configuration from {default_config_file}")
            except Exception as e:
                logger.warning(f"Error loading default configuration from {default_config_file}: {e}")

    # Create the configuration object
    return Configuration.from_dict(config_dict) 