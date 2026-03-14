from __future__ import annotations

import typer

from jp_anki_builder.build import NoBuildableWordsError
from jp_anki_builder.dict_install import DEFAULT_JMDICT_E_URL, install_jmdict_offline_json, install_jlpt_from_file
from jp_anki_builder.path_inference import infer_source_and_run_id
from jp_anki_builder.pipeline import Pipeline
from jp_anki_builder.project_config import VALID_KEYS, get_config, load_project_config, set_config, unset_config
from jp_anki_builder.review import prepare_review

app = typer.Typer()
config_app = typer.Typer(help="View and update project/source configuration.")
app.add_typer(config_app, name="config")
WORD_PREVIEW_LIMIT = 10


def _parse_selected_indices(raw: str, max_value: int) -> list[int]:
    raw = raw.strip()
    if not raw:
        return []

    indices: list[int] = []
    for chunk in raw.split(","):
        part = chunk.strip()
        if not part:
            continue
        if not part.isdigit():
            raise ValueError(f"Invalid index value: {part}")
        index = int(part)
        if index < 1 or index > max_value:
            raise ValueError(f"Index out of range: {index}")
        indices.append(index)
    return sorted(set(indices))


def _emit_stage_header(stage: str) -> None:
    typer.echo(f"[{stage}]")


def _format_word_preview(words: list[str], limit: int = WORD_PREVIEW_LIMIT) -> str:
    if not words:
        return "(none)"
    shown = words[:limit]
    remainder = len(words) - len(shown)
    text = ", ".join(shown)
    if remainder > 0:
        text += f", (+{remainder} more)"
    return text


def _emit_reason_bucket(label: str, words: list[str]) -> None:
    if not words:
        return
    typer.echo(f"[WARN] {label} ({len(words)}): {_format_word_preview(words)}")


def _emit_empty_build_guidance(missing_meaning_words: list[str]) -> None:
    _emit_stage_header("BUILD")
    typer.echo("[WARN] No cards were created for this run.")
    _emit_reason_bucket("Missing meaning", missing_meaning_words)
    typer.echo("[NEXT] Add meanings to data/dictionaries/offline.json")
    typer.echo("[NEXT] Or rerun with --online-dict jisho")


def _resolve_defaults(images: str, source: str | None, run_id: str | None,
                      data_dir: str, ocr_mode: str | None, ocr_language: str | None,
                      online_dict: str | None, no_preprocess: bool | None,
                      volume: str | None = None, chapter: str | None = None,
                      ) -> dict:
    """Resolve CLI args with config-file defaults and path inference."""
    # Load config-file defaults (project-level, then source-level)
    cfg = load_project_config(data_dir=data_dir, source=source)

    # Auto-derive source/run_id from images path if not provided
    if source is None or run_id is None:
        inferred_source, inferred_run_id = infer_source_and_run_id(images)
        if source is None:
            source = inferred_source
        if run_id is None:
            run_id = inferred_run_id

    if source is None:
        raise typer.BadParameter(
            "Cannot infer --source from image path. Please provide it explicitly.",
            param_hint="--source",
        )
    if run_id is None:
        raise typer.BadParameter(
            "Cannot infer --run-id from image path. Please provide it explicitly.",
            param_hint="--run-id",
        )

    return {
        "source": source,
        "run_id": run_id,
        "ocr_mode": ocr_mode or cfg.ocr_mode or "manga-ocr",
        "ocr_language": ocr_language or cfg.ocr_language or "jpn",
        "online_dict": online_dict or cfg.online_dict or "off",
        "no_preprocess": no_preprocess if no_preprocess is not None else (cfg.no_preprocess or False),
        "volume": volume or cfg.volume,
        "chapter": chapter or cfg.chapter,
    }


@app.command()
def scan(
    images: str = typer.Option(..., help="Image file or directory path."),
    source: str | None = typer.Option(None, help="Source id (auto-derived from path if omitted)."),
    run_id: str | None = typer.Option(None, help="Run id (auto-derived from path if omitted)."),
    data_dir: str = typer.Option("data", help="Data storage directory."),
    ocr_mode: str | None = typer.Option(None, help="OCR backend: tesseract, manga-ocr, or sidecar."),
    ocr_language: str | None = typer.Option(None, help="OCR language code (tesseract mode)."),
    tesseract_cmd: str | None = typer.Option(
        None,
        help="Optional full path to tesseract executable.",
    ),
    no_preprocess: bool | None = typer.Option(
        None,
        "--no-preprocess",
        help="Disable basic OCR image preprocessing.",
    ),
    online_dict: str | None = typer.Option(None, help="Online fallback dictionary for compound detection: off or jisho."),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Resume a previously interrupted scan, skipping already-processed images.",
    ),
) -> None:
    """Scan screenshots and produce OCR/candidate artifacts."""
    d = _resolve_defaults(
        images=images, source=source, run_id=run_id, data_dir=data_dir,
        ocr_mode=ocr_mode, ocr_language=ocr_language, online_dict=online_dict,
        no_preprocess=no_preprocess,
    )
    try:
        result = Pipeline(data_dir=data_dir).scan(
            images=images,
            source=d["source"],
            run_id=d["run_id"],
            ocr_mode=d["ocr_mode"],
            ocr_language=d["ocr_language"],
            tesseract_cmd=tesseract_cmd,
            preprocess=not d["no_preprocess"],
            online_dict=d["online_dict"],
            resume=resume,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--images") from exc
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc), param_hint="--ocr-mode") from exc

    _emit_stage_header("SCAN")
    if result.get("resumed"):
        typer.echo("[INFO] Resumed from previous partial scan.")
    typer.echo(f"[OK] I processed {result['image_count']} image(s).")
    typer.echo(f"[OK] I found {result['candidate_count']} candidate word(s).")
    typer.echo(f"[INFO] Candidate preview: {_format_word_preview(result.get('candidates', []))}")
    typer.echo(f"[INFO] Saved scan results to: {result['artifact_path']}")


@app.command()
def review(
    source: str = typer.Option(..., help="Top-level source id, e.g. game or manga name."),
    run_id: str = typer.Option(..., help="Run id created by scan."),
    data_dir: str = typer.Option("data", help="Data storage directory."),
    exclude: list[str] = typer.Option(None, help="Words to exclude manually (repeatable)."),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        help="Show candidate list and choose exclusions by index.",
    ),
    save_excluded_to_known: bool = typer.Option(
        False,
        "--save-excluded-to-known",
        help="Append manually excluded words to data/<source>/known_words.txt.",
    ),
) -> None:
    """Review and approve candidate words."""
    manual_excludes = set(exclude or [])

    if interactive:
        plan = prepare_review(source=source, run_id=run_id, base_dir=data_dir)
        typer.echo("Filtered candidates:")
        for idx, word in enumerate(plan.filtered_candidates, start=1):
            typer.echo(f"{idx}. {word}")

        if plan.filtered_candidates:
            selection = typer.prompt(
                "Enter indices to exclude (comma-separated, blank for none)",
                default="",
                show_default=False,
            )
            try:
                selected_indices = _parse_selected_indices(selection, len(plan.filtered_candidates))
            except ValueError as exc:
                raise typer.BadParameter(str(exc), param_hint="--interactive") from exc

            for idx in selected_indices:
                manual_excludes.add(plan.filtered_candidates[idx - 1])

            if manual_excludes and not save_excluded_to_known:
                save_excluded_to_known = typer.confirm(
                    "Save excluded words to data/<source>/known_words.txt?",
                    default=False,
                )

    result = Pipeline(data_dir=data_dir).review(
        source=source,
        run_id=run_id,
        exclude=sorted(manual_excludes),
        save_excluded_to_known=save_excluded_to_known,
    )
    _emit_stage_header("REVIEW")
    typer.echo(
        f"[OK] I approved {result['approved_count']} of {result['initial_count']} candidate(s) for card building."
    )
    _emit_reason_bucket("Known", result.get("excluded_known", []))
    _emit_reason_bucket("Particle", result.get("excluded_particles", []))
    _emit_reason_bucket("Already seen", result.get("excluded_seen", []))
    _emit_reason_bucket("Manual exclude", result.get("excluded_manual", []))
    typer.echo(f"[INFO] Saved review results to: {result['artifact_path']}")


@app.command()
def build(
    source: str = typer.Option(..., help="Top-level source id, e.g. game or manga name."),
    run_id: str = typer.Option(..., help="Run id created by scan/review."),
    data_dir: str = typer.Option("data", help="Data storage directory."),
    volume: str | None = typer.Option(None, help="Optional volume label, e.g. 02."),
    chapter: str | None = typer.Option(None, help="Optional chapter label, e.g. 07."),
    online_dict: str = typer.Option("off", help="Online fallback dictionary: off or jisho."),
) -> None:
    """Build Anki package from approved words."""
    try:
        result = Pipeline(data_dir=data_dir).build(
            source=source,
            run_id=run_id,
            volume=volume,
            chapter=chapter,
            online_dict=online_dict,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--run-id") from exc
    except NoBuildableWordsError as exc:
        _emit_empty_build_guidance(exc.missing_meaning_words)
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.echo(f"Build failed: {exc}")
        raise typer.Exit(code=1) from exc

    _emit_stage_header("BUILD")
    typer.echo(
        f"[OK] I created cards for {result['buildable_word_count']} word(s): "
        f"{_format_word_preview(result.get('buildable_words', []))}"
    )
    _emit_reason_bucket("Missing meaning", result.get("missing_meaning_words", []))
    typer.echo("[OK] Deck package created.")
    typer.echo(f"[INFO] Package: {result['package_path']}")
    typer.echo(f"[INFO] Build details: {result['artifact_path']}")


@app.command()
def run(
    images: str = typer.Option(..., help="Image file or directory path."),
    source: str | None = typer.Option(None, help="Source id (auto-derived from path if omitted)."),
    run_id: str | None = typer.Option(None, help="Run id (auto-derived from path if omitted)."),
    data_dir: str = typer.Option("data", help="Data storage directory."),
    ocr_mode: str | None = typer.Option(None, help="OCR backend: tesseract, manga-ocr, or sidecar."),
    ocr_language: str | None = typer.Option(None, help="OCR language code (tesseract mode)."),
    tesseract_cmd: str | None = typer.Option(
        None,
        help="Optional full path to tesseract executable.",
    ),
    no_preprocess: bool | None = typer.Option(
        None,
        "--no-preprocess",
        help="Disable basic OCR image preprocessing.",
    ),
    exclude: list[str] = typer.Option(None, help="Words to exclude manually (repeatable)."),
    save_excluded_to_known: bool = typer.Option(
        False,
        "--save-excluded-to-known",
        help="Append manually excluded words to data/<source>/known_words.txt.",
    ),
    volume: str | None = typer.Option(None, help="Optional volume label, e.g. 02."),
    chapter: str | None = typer.Option(None, help="Optional chapter label, e.g. 07."),
    online_dict: str | None = typer.Option(None, help="Online fallback dictionary: off or jisho."),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Resume a previously interrupted scan, skipping already-processed images.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would happen without writing artifacts or generating a deck.",
    ),
) -> None:
    """Run scan -> review -> build."""
    d = _resolve_defaults(
        images=images, source=source, run_id=run_id, data_dir=data_dir,
        ocr_mode=ocr_mode, ocr_language=ocr_language, online_dict=online_dict,
        no_preprocess=no_preprocess, volume=volume, chapter=chapter,
    )
    pipeline = Pipeline(data_dir=data_dir)
    try:
        scan_result = pipeline.scan(
            images=images,
            source=d["source"],
            run_id=d["run_id"],
            ocr_mode=d["ocr_mode"],
            ocr_language=d["ocr_language"],
            tesseract_cmd=tesseract_cmd,
            preprocess=not d["no_preprocess"],
            online_dict=d["online_dict"],
            resume=resume,
        )
        _emit_stage_header("SCAN")
        typer.echo(
            f"[OK] I processed {scan_result['image_count']} image(s)."
        )
        typer.echo(f"[OK] I found {scan_result['candidate_count']} candidate word(s).")
        typer.echo(f"[INFO] Candidate preview: {_format_word_preview(scan_result.get('candidates', []))}")
        if scan_result["candidate_count"] == 0:
            typer.echo("[WARN] No candidates detected in scan stage.")
            raise typer.Exit(code=1)

        if dry_run:
            # In dry-run mode, compute the review plan without writing artifacts
            from jp_anki_builder.review import prepare_review as _prepare_review

            plan = _prepare_review(source=d["source"], run_id=d["run_id"], base_dir=data_dir)
            _emit_stage_header("REVIEW (dry-run)")
            typer.echo(
                f"[OK] Would approve {len(plan.filtered_candidates)} of "
                f"{len(plan.initial_candidates)} candidate(s)."
            )
            _emit_reason_bucket("Known", plan.excluded_known)
            _emit_reason_bucket("Particle", plan.excluded_particles)
            _emit_reason_bucket("Already seen", plan.excluded_seen)
            if plan.filtered_candidates:
                typer.echo(f"[INFO] Approved preview: {_format_word_preview(plan.filtered_candidates)}")

            _emit_stage_header("BUILD (dry-run)")
            typer.echo("[INFO] Would attempt to build deck from approved words.")
            typer.echo("[INFO] No artifacts written. Remove --dry-run to execute.")
            return

        review_result = pipeline.review(
            source=d["source"],
            run_id=d["run_id"],
            exclude=exclude,
            save_excluded_to_known=save_excluded_to_known,
        )
        _emit_stage_header("REVIEW")
        typer.echo(
            f"[OK] I approved {review_result['approved_count']} of {review_result['initial_count']} candidate(s) for card building."
        )
        _emit_reason_bucket("Known", review_result.get("excluded_known", []))
        _emit_reason_bucket("Particle", review_result.get("excluded_particles", []))
        _emit_reason_bucket("Already seen", review_result.get("excluded_seen", []))
        _emit_reason_bucket("Manual exclude", review_result.get("excluded_manual", []))
        if review_result["approved_count"] == 0:
            typer.echo("[WARN] No approved words remain after review.")
            raise typer.Exit(code=1)

        build_result = pipeline.build(
            source=d["source"],
            run_id=d["run_id"],
            volume=d["volume"],
            chapter=d["chapter"],
            online_dict=d["online_dict"],
        )
    except NoBuildableWordsError as exc:
        _emit_empty_build_guidance(exc.missing_meaning_words)
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except RuntimeError as exc:
        typer.echo(f"Run failed: {exc}")
        raise typer.Exit(code=1) from exc

    _emit_stage_header("BUILD")
    typer.echo(
        f"[OK] I created cards for {build_result['buildable_word_count']} word(s): "
        f"{_format_word_preview(build_result.get('buildable_words', []))}"
    )
    _emit_reason_bucket("Missing meaning", build_result.get("missing_meaning_words", []))
    typer.echo("[OK] Deck package created.")
    typer.echo(f"[INFO] Package: {build_result['package_path']}")

    _emit_stage_header("RUN")
    typer.echo("[OK] Pipeline finished: scan -> review -> build")
    typer.echo(
        f"[INFO] Totals: {scan_result['candidate_count']} candidates, "
        f"{review_result['approved_count']} approved, "
        f"{build_result['note_count']} notes created"
    )


@app.command("install-dictionary")
def install_dictionary(
    data_dir: str = typer.Option("data", help="Data storage directory."),
    provider: str = typer.Option("jmdict", help="Dictionary provider to install."),
    source_url: str = typer.Option(
        DEFAULT_JMDICT_E_URL,
        help="Source URL for the dictionary download.",
    ),
    max_meanings: int = typer.Option(3, help="Max meanings stored per entry."),
) -> None:
    """Install a local offline dictionary into data/dictionaries/offline.json."""
    if provider != "jmdict":
        raise typer.BadParameter("Unsupported provider. Use: jmdict")

    _emit_stage_header("DICTIONARY")
    typer.echo("[INFO] Installing JMdict offline dictionary. This can take a few minutes.")
    try:
        summary = install_jmdict_offline_json(
            base_dir=data_dir,
            source_url=source_url,
            max_meanings=max_meanings,
        )
    except Exception as exc:
        typer.echo(f"[WARN] Dictionary install failed: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"[OK] Installed provider: {summary.provider}")
    typer.echo(f"[OK] Entries written: {summary.entry_count}")
    typer.echo(f"[INFO] Output: {summary.output_path}")


@app.command("migrate-dictionary")
def migrate_dictionary(
    data_dir: str = typer.Option("data", help="Data storage directory."),
) -> None:
    """Migrate offline.json to offline.db (SQLite) for faster lookups and lower memory."""
    from pathlib import Path

    from jp_anki_builder.dictionary import OfflineSqliteDictionary

    json_path = Path(data_dir) / "dictionaries" / "offline.json"
    sqlite_path = Path(data_dir) / "dictionaries" / "offline.db"

    if not json_path.exists():
        typer.echo(f"[WARN] Source not found: {json_path}")
        raise typer.Exit(code=1)

    _emit_stage_header("MIGRATE")
    count = OfflineSqliteDictionary.create_from_json(json_path, sqlite_path)
    typer.echo(f"[OK] Migrated {count} entries to SQLite: {sqlite_path}")
    typer.echo("[INFO] The SQLite dictionary will be used automatically.")


@app.command("install-jlpt")
def install_jlpt(
    source_file: str = typer.Option(..., help="Path to JLPT JSON file mapping words to levels 1-5."),
    data_dir: str = typer.Option("data", help="Data storage directory."),
) -> None:
    """Install JLPT level data from a JSON file into data/dictionaries/jlpt_levels.json."""
    _emit_stage_header("JLPT")
    try:
        summary = install_jlpt_from_file(
            source_path=source_file,
            base_dir=data_dir,
        )
    except Exception as exc:
        typer.echo(f"[WARN] JLPT install failed: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"[OK] Installed JLPT data: {summary.entry_count} entries")
    typer.echo(f"[INFO] Output: {summary.output_path}")


@config_app.command("show")
def config_show(
    data_dir: str = typer.Option("data", help="Data storage directory."),
    source: str | None = typer.Option(None, help="Show source-level config instead of project-level."),
) -> None:
    """Show current configuration."""
    cfg = get_config(data_dir=data_dir, source=source)
    level = f"source ({source})" if source else "project"
    if not cfg:
        typer.echo(f"[INFO] No {level} config set.")
        typer.echo(f"[INFO] Valid keys: {', '.join(sorted(VALID_KEYS))}")
        return
    _emit_stage_header(f"CONFIG ({level})")
    for key, value in sorted(cfg.items()):
        typer.echo(f"  {key} = {value}")


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Config key to set."),
    value: str = typer.Argument(help="Value to set."),
    data_dir: str = typer.Option("data", help="Data storage directory."),
    source: str | None = typer.Option(None, help="Set on source-level config instead of project-level."),
) -> None:
    """Set a configuration value."""
    try:
        updated = set_config(key, value, data_dir=data_dir, source=source)
    except ValueError as exc:
        typer.echo(f"[WARN] {exc}")
        raise typer.Exit(code=1) from exc
    level = f"source ({source})" if source else "project"
    typer.echo(f"[OK] {level}: {key} = {updated[key]}")


@config_app.command("unset")
def config_unset(
    key: str = typer.Argument(help="Config key to remove."),
    data_dir: str = typer.Option("data", help="Data storage directory."),
    source: str | None = typer.Option(None, help="Unset from source-level config instead of project-level."),
) -> None:
    """Remove a configuration value."""
    unset_config(key, data_dir=data_dir, source=source)
    level = f"source ({source})" if source else "project"
    typer.echo(f"[OK] {level}: removed {key}")


if __name__ == "__main__":
    app()
