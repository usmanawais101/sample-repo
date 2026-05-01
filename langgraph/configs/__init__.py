"""Configuration module."""

import os
import yaml
from pathlib import Path
from typing import Any, Dict


def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to config file (defaults to configs/config.yaml)
    
    Returns:
        Configuration dictionary
    """
    if config_path is None:
        # Default to config.yaml in the configs directory
        config_path = Path(__file__).parent / "config.yaml"
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


__all__ = ["load_config"]
