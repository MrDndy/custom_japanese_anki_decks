from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunPaths:
    base_dir: str
    source_id: str
    run_id: str

    @property
    def run_dir(self) -> Path:
        return Path(self.base_dir) / "runs" / self.run_id

    @property
    def source_seen_words(self) -> Path:
        return Path(self.base_dir) / "sources" / self.source_id / "seen_words.json"
