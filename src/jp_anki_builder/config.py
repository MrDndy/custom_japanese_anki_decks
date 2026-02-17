from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunPaths:
    base_dir: str
    source_id: str
    run_id: str

    @property
    def run_dir(self) -> Path:
        return Path(self.base_dir) / self.source_id / self.run_id

    @property
    def source_seen_words(self) -> Path:
        return Path(self.base_dir) / self.source_id / "seen_words.json"

    @property
    def scan_artifact(self) -> Path:
        return self.run_dir / "scan.json"

    @property
    def review_artifact(self) -> Path:
        return self.run_dir / "review.json"

    @property
    def known_words(self) -> Path:
        return Path(self.base_dir) / self.source_id / "known_words.txt"

    @property
    def build_artifact(self) -> Path:
        return self.run_dir / "build.json"

    @property
    def deck_package(self) -> Path:
        return self.run_dir / "deck.apkg"
