"""QThread workers for running pipeline stages off the main thread."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from jp_anki_builder.pipeline import Pipeline

logger = logging.getLogger(__name__)

_PYSIDE6_AVAILABLE = False

try:
    from PySide6.QtCore import QThread, Signal

    _PYSIDE6_AVAILABLE = True

    # -----------------------------------------------------------------------
    # ScanWorker — runs Pipeline.scan() off the main thread
    # -----------------------------------------------------------------------

    class ScanWorker(QThread):
        """Runs the scan stage in a worker thread."""

        log_message = Signal(str)
        scan_finished = Signal(dict)
        error = Signal(str)

        def __init__(
            self,
            pipeline: Pipeline,
            images: str,
            source: str,
            run_id: str,
            ocr_mode: str = "manga-ocr",
            detector_mode: str = "none",
        ) -> None:
            super().__init__()
            self._pipeline = pipeline
            self._images = images
            self._source = source
            self._run_id = run_id
            self._ocr_mode = ocr_mode
            self._detector_mode = detector_mode

        def run(self) -> None:
            try:
                self.log_message.emit(
                    f"[SCAN] Starting scan: {self._images} "
                    f"(ocr={self._ocr_mode}, detector={self._detector_mode})"
                )
                result = self._pipeline.scan(
                    images=self._images,
                    source=self._source,
                    run_id=self._run_id,
                    ocr_mode=self._ocr_mode,
                    detector_mode=self._detector_mode,
                )
                self.log_message.emit(
                    f"[SCAN] Complete: {result['candidate_count']} candidates found."
                )
                self.scan_finished.emit(result)
            except Exception as exc:
                logger.exception("ScanWorker error")
                self.error.emit(str(exc))

    # -----------------------------------------------------------------------
    # SubScanWorker — runs subtitle extraction + scan off the main thread
    # -----------------------------------------------------------------------

    class SubScanWorker(QThread):
        """Runs subtitle-based scan in a worker thread."""

        log_message = Signal(str)
        scan_finished = Signal(dict)
        error = Signal(str)

        def __init__(
            self,
            video: str,
            source: str,
            run_id: str,
            data_dir: str = "data",
        ) -> None:
            super().__init__()
            self._video = video
            self._source = source
            self._run_id = run_id
            self._data_dir = data_dir

        def run(self) -> None:
            from jp_anki_builder.subtitle_extractor import run_scan_subs

            try:
                self.log_message.emit(f"[SCAN-SUBS] Extracting subtitles: {self._video}")
                summary = run_scan_subs(
                    video=self._video,
                    source=self._source,
                    run_id=self._run_id,
                    base_dir=self._data_dir,
                )
                result = {
                    "stage": "scan",
                    "run_id": summary.run_id,
                    "image_count": summary.image_count,
                    "candidate_count": summary.candidate_count,
                    "candidates": summary.candidates,
                    "artifact_path": str(summary.artifact_path),
                }
                self.log_message.emit(
                    f"[SCAN-SUBS] Complete: {result['candidate_count']} candidates found."
                )
                self.scan_finished.emit(result)
            except Exception as exc:
                logger.exception("SubScanWorker error")
                self.error.emit(str(exc))

    # -----------------------------------------------------------------------
    # BuildWorker — writes review.json from approved list, then builds deck
    # -----------------------------------------------------------------------

    class BuildWorker(QThread):
        """Writes review artifact from approved word list, then runs Pipeline.build()."""

        log_message = Signal(str)
        build_finished = Signal(dict)
        error = Signal(str)

        def __init__(
            self,
            pipeline: Pipeline,
            source: str,
            run_id: str,
            approved_words: list[str],
            volume: str | None = None,
            chapter: str | None = None,
        ) -> None:
            super().__init__()
            self._pipeline = pipeline
            self._source = source
            self._run_id = run_id
            self._approved_words = approved_words
            self._volume = volume
            self._chapter = chapter

        def run(self) -> None:
            from jp_anki_builder.build import NoBuildableWordsError
            from jp_anki_builder.config import RunPaths

            try:
                # Write review.json with approved candidates so Pipeline.build() can read it.
                paths = RunPaths(
                    base_dir=self._pipeline.data_dir,
                    source_id=self._source,
                    run_id=self._run_id,
                )
                review_payload = {
                    "source": self._source,
                    "run_id": self._run_id,
                    "approved_candidates": self._approved_words,
                    "approved_candidates_meta": {},
                    "low_confidence_candidates": [],
                    "excluded_known": [],
                    "excluded_particles": [],
                    "excluded_seen": [],
                    "excluded_sfx": [],
                    "excluded_furigana": [],
                    "excluded_manual": [],
                }
                paths.review_artifact.parent.mkdir(parents=True, exist_ok=True)
                paths.review_artifact.write_text(
                    json.dumps(review_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                self.log_message.emit(
                    f"[BUILD] Building deck for {len(self._approved_words)} approved words…"
                )
                result = self._pipeline.build(
                    source=self._source,
                    run_id=self._run_id,
                    volume=self._volume,
                    chapter=self._chapter,
                )
                self.log_message.emit(
                    f"[BUILD] Complete: {result['buildable_word_count']} cards. "
                    f"Package: {result['package_path']}"
                )
                self.build_finished.emit(result)
            except Exception as exc:
                logger.exception("BuildWorker error")
                self.error.emit(str(exc))

    # -----------------------------------------------------------------------
    # RunAllWorker — runs scan → auto-review → build in one shot
    # -----------------------------------------------------------------------

    class RunAllWorker(QThread):
        """Runs the full scan → review → build pipeline without interactive review."""

        log_message = Signal(str)
        run_finished = Signal(dict)
        error = Signal(str)

        def __init__(
            self,
            pipeline: Pipeline,
            images: str,
            source: str,
            run_id: str,
            ocr_mode: str = "manga-ocr",
            detector_mode: str = "none",
            volume: str | None = None,
            chapter: str | None = None,
        ) -> None:
            super().__init__()
            self._pipeline = pipeline
            self._images = images
            self._source = source
            self._run_id = run_id
            self._ocr_mode = ocr_mode
            self._detector_mode = detector_mode
            self._volume = volume
            self._chapter = chapter

        def run(self) -> None:
            try:
                self.log_message.emit(f"[RUN ALL] Starting full pipeline: {self._images}")
                result = self._pipeline.run_all(
                    images=self._images,
                    source=self._source,
                    run_id=self._run_id,
                    ocr_mode=self._ocr_mode,
                    detector_mode=self._detector_mode,
                    volume=self._volume,
                    chapter=self._chapter,
                )
                build = result.get("build", {})
                self.log_message.emit(
                    f"[RUN ALL] Complete: {build.get('buildable_word_count', 0)} cards created. "
                    f"Package: {build.get('package_path', '')}"
                )
                self.run_finished.emit(result)
            except Exception as exc:
                logger.exception("RunAllWorker error")
                self.error.emit(str(exc))

    # -----------------------------------------------------------------------
    # DictInstallWorker — installs JMdict dictionary off the main thread
    # -----------------------------------------------------------------------

    class DictInstallWorker(QThread):
        """Downloads and installs the JMdict offline dictionary in a worker thread."""

        log_message = Signal(str)
        install_finished = Signal(str)
        error = Signal(str)

        def __init__(self, data_dir: str = "data") -> None:
            super().__init__()
            self._data_dir = data_dir

        def run(self) -> None:
            from jp_anki_builder.dict_install import install_jmdict_offline_json

            try:
                self.log_message.emit("[DICT] Installing JMdict dictionary…")
                summary = install_jmdict_offline_json(base_dir=self._data_dir)
                self.install_finished.emit(
                    f"JMdict installed: {summary.entry_count} entries at {summary.output_path}"
                )
            except Exception as exc:
                logger.exception("DictInstallWorker error")
                self.error.emit(str(exc))

except ImportError:
    pass  # Workers are only instantiated from within the PySide6 try block in main_window.py
