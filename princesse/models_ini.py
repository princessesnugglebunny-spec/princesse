"""models.ini (llama-server preset) management with atomic writes and backups."""

from __future__ import annotations

import configparser
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


class ModelsIni:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.config = configparser.ConfigParser()
        if self.path.exists():
            self.config.read(self.path)

    def sections(self) -> list[str]:
        return self.config.sections()

    def get_section(self, name: str) -> dict[str, str]:
        if not self.config.has_section(name):
            return {}
        return dict(self.config[name])

    def set_section(self, name: str, values: dict[str, Any]):
        if not self.config.has_section(name):
            self.config.add_section(name)
        for k, v in values.items():
            self.config.set(name, str(k), str(v))

    def remove_section(self, name: str) -> bool:
        return self.config.remove_section(name)

    def save(self, backup: bool = True):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if backup and self.path.exists():
            ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            backup_path = self.path.with_suffix(self.path.suffix + f".{ts}.bak")
            shutil.copy2(self.path, backup_path)
            # keep only 10 backups
            backups = sorted(self.path.parent.glob(self.path.name + ".*.bak"))
            for old in backups[:-10]:
                try:
                    old.unlink()
                except OSError:
                    pass
        with self.path.open("w") as f:
            self.config.write(f)

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {s: dict(self.config[s]) for s in self.config.sections()}
