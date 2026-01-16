"""Configuration management for Pluribus workspaces."""

from pathlib import Path
from typing import Optional


class Config:
    """Manages pluribus.config file."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)
        self.config_file = self.workspace_root / "pluribus.config"

    def load(self) -> dict:
        """Load config from file. Returns empty dict if file doesn't exist."""
        if not self.config_file.exists():
            return {}

        with open(self.config_file) as f:
            content = f.read()
            # Simple key=value parsing (not full TOML for minimal dependency)
            config = {}
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('['):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"')
                    config[key] = value
            return config

    def save(self, config: dict) -> None:
        """Save config to file."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for key, value in config.items():
            lines.append(f'{key} = "{value}"')

        with open(self.config_file, 'w') as f:
            f.write('[pluribus]\n')
            f.write('\n'.join(lines))

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
