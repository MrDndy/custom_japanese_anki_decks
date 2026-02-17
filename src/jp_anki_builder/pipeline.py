from __future__ import annotations

from dataclasses import dataclass

from jp_anki_builder.build import run_build
from jp_anki_builder.review import run_review
from jp_anki_builder.scan import run_scan


@dataclass
class Pipeline:
    data_dir: str = "data"

    def scan(
        self,
        images: str,
        source: str,
        run_id: str,
        ocr_mode: str = "sidecar",
        ocr_language: str = "jpn",
        tesseract_cmd: str | None = None,
        preprocess: bool = True,
        online_dict: str = "off",
    ) -> dict:
        summary = run_scan(
            images=images,
            source=source,
            run_id=run_id,
            base_dir=self.data_dir,
            ocr_mode=ocr_mode,
            ocr_language=ocr_language,
            tesseract_cmd=tesseract_cmd,
            preprocess=preprocess,
            online_dict=online_dict,
        )
        return {
            "stage": "scan",
            "run_id": summary.run_id,
            "image_count": summary.image_count,
            "candidate_count": summary.candidate_count,
            "candidates": summary.candidates,
            "artifact_path": str(summary.artifact_path),
        }

    def review(
        self,
        source: str,
        run_id: str,
        exclude: list[str] | None = None,
        save_excluded_to_known: bool = False,
    ) -> dict:
        summary = run_review(
            source=source,
            run_id=run_id,
            base_dir=self.data_dir,
            exclude=exclude,
            save_excluded_to_known=save_excluded_to_known,
        )
        return {
            "stage": "review",
            "run_id": summary.run_id,
            "source": summary.source,
            "initial_count": summary.initial_count,
            "approved_count": summary.approved_count,
            "excluded_known": summary.excluded_known,
            "excluded_particles": summary.excluded_particles,
            "excluded_seen": summary.excluded_seen,
            "excluded_manual": summary.excluded_manual,
            "artifact_path": summary.review_artifact_path,
        }

    def build(
        self,
        source: str,
        run_id: str,
        volume: str | None = None,
        chapter: str | None = None,
        online_dict: str = "off",
    ) -> dict:
        summary = run_build(
            source=source,
            run_id=run_id,
            base_dir=self.data_dir,
            volume=volume,
            chapter=chapter,
            online_dict=online_dict,
        )
        return {
            "stage": "build",
            "run_id": summary.run_id,
            "source": summary.source,
            "note_count": summary.note_count,
            "approved_word_count": summary.approved_word_count,
            "buildable_word_count": summary.buildable_word_count,
            "missing_meaning_words": summary.missing_meaning_words,
            "buildable_words": summary.buildable_words,
            "package_path": summary.package_path,
            "artifact_path": summary.artifact_path,
        }

    def run_all(
        self,
        images: str,
        source: str,
        run_id: str,
        ocr_mode: str = "sidecar",
        ocr_language: str = "jpn",
        tesseract_cmd: str | None = None,
        preprocess: bool = True,
        exclude: list[str] | None = None,
        save_excluded_to_known: bool = False,
        volume: str | None = None,
        chapter: str | None = None,
        online_dict: str = "off",
    ) -> dict:
        scan_result = self.scan(
            images=images,
            source=source,
            run_id=run_id,
            ocr_mode=ocr_mode,
            ocr_language=ocr_language,
            tesseract_cmd=tesseract_cmd,
            preprocess=preprocess,
            online_dict=online_dict,
        )
        review_result = self.review(
            source=source,
            run_id=run_id,
            exclude=exclude,
            save_excluded_to_known=save_excluded_to_known,
        )
        build_result = self.build(
            source=source,
            run_id=run_id,
            volume=volume,
            chapter=chapter,
            online_dict=online_dict,
        )
        return {
            "scan": scan_result,
            "review": review_result,
            "build": build_result,
        }
