"""Configuration management for Pluribus workspaces."""

from pathlib import Path
from typing import Optional

import yaml


class Config:
    """Manages pluribus.config file in YAML format."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)
        self.config_file = self.workspace_root / "pluribus.config"

    def load(self) -> dict:
        """Load config from YAML file. Returns empty dict if file doesn't exist."""
        if not self.config_file.exists():
            return {}

        try:
            with open(self.config_file) as f:
                content = yaml.safe_load(f)
                return content if content else {}
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse pluribus.config: {e}") from e

    def save(self, config: dict) -> None:
        """Save config to YAML file."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    def get_repo_path(self) -> Optional[Path]:
        """Get repo path from config."""
        config = self.load()
        if 'repo_path' in config:
            return Path(config['repo_path'])
        return None

    def get_repo_url(self) -> Optional[str]:
        """Get repo URL from config."""
        config = self.load()
        return config.get('repo_url')
