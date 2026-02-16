from __future__ import annotations

import typer

from jp_anki_builder.pipeline import Pipeline
from jp_anki_builder.review import prepare_review

app = typer.Typer()


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


@app.command()
def scan(
    images: str = typer.Option(..., help="Image file or directory path."),
    source: str = typer.Option(..., help="Top-level source id, e.g. game or manga name."),
    run_id: str = typer.Option(..., help="Unique run id, e.g. mangaa-ch01."),
    data_dir: str = typer.Option("data", help="Data storage directory."),
    ocr_mode: str = typer.Option("tesseract", help="OCR backend: tesseract, manga-ocr, or sidecar."),
    ocr_language: str = typer.Option("jpn", help="OCR language code (tesseract mode)."),
    tesseract_cmd: str | None = typer.Option(
        None,
        help="Optional full path to tesseract executable.",
    ),
    no_preprocess: bool = typer.Option(
        False,
        "--no-preprocess",
        help="Disable basic OCR image preprocessing.",
    ),
) -> None:
    """Scan screenshots and produce OCR/candidate artifacts."""
    try:
        result = Pipeline(data_dir=data_dir).scan(
            images=images,
            source=source,
            run_id=run_id,
            ocr_mode=ocr_mode,
            ocr_language=ocr_language,
            tesseract_cmd=tesseract_cmd,
            preprocess=not no_preprocess,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--images") from exc
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc), param_hint="--ocr-mode") from exc

    typer.echo(f"scan complete: {result['image_count']} image(s), {result['candidate_count']} candidate(s)")
    typer.echo(f"artifact: {result['artifact_path']}")


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
        help="Append manually excluded words to known_words.txt.",
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
                    "Save excluded words to known_words.txt?",
                    default=False,
                )

    result = Pipeline(data_dir=data_dir).review(
        source=source,
        run_id=run_id,
        exclude=sorted(manual_excludes),
        save_excluded_to_known=save_excluded_to_known,
    )
    typer.echo(
        "review complete: "
        f"{result['approved_count']}/{result['initial_count']} approved candidate(s)"
    )
    typer.echo(f"artifact: {result['artifact_path']}")


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
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc), param_hint="--data-dir") from exc

    typer.echo(f"build complete: {result['note_count']} note(s)")
    typer.echo(f"package: {result['package_path']}")
    typer.echo(f"artifact: {result['artifact_path']}")


@app.command()
def run(
    images: str = typer.Option(..., help="Image file or directory path."),
    source: str = typer.Option(..., help="Top-level source id, e.g. game or manga name."),
    run_id: str = typer.Option(..., help="Unique run id, e.g. mangaa-ch01."),
    data_dir: str = typer.Option("data", help="Data storage directory."),
    ocr_mode: str = typer.Option("tesseract", help="OCR backend: tesseract, manga-ocr, or sidecar."),
    ocr_language: str = typer.Option("jpn", help="OCR language code (tesseract mode)."),
    tesseract_cmd: str | None = typer.Option(
        None,
        help="Optional full path to tesseract executable.",
    ),
    no_preprocess: bool = typer.Option(
        False,
        "--no-preprocess",
        help="Disable basic OCR image preprocessing.",
    ),
    exclude: list[str] = typer.Option(None, help="Words to exclude manually (repeatable)."),
    save_excluded_to_known: bool = typer.Option(
        False,
        "--save-excluded-to-known",
        help="Append manually excluded words to known_words.txt.",
    ),
    volume: str | None = typer.Option(None, help="Optional volume label, e.g. 02."),
    chapter: str | None = typer.Option(None, help="Optional chapter label, e.g. 07."),
    online_dict: str = typer.Option("off", help="Online fallback dictionary: off or jisho."),
) -> None:
    """Run scan -> review -> build."""
    try:
        result = Pipeline(data_dir=data_dir).run_all(
            images=images,
            source=source,
            run_id=run_id,
            ocr_mode=ocr_mode,
            ocr_language=ocr_language,
            tesseract_cmd=tesseract_cmd,
            preprocess=not no_preprocess,
            exclude=exclude,
            save_excluded_to_known=save_excluded_to_known,
            volume=volume,
            chapter=chapter,
            online_dict=online_dict,
        )
    except (ValueError, RuntimeError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(
        "run complete: "
        f"{result['scan']['image_count']} image(s), "
        f"{result['review']['approved_count']} approved candidate(s), "
        f"{result['build']['note_count']} note(s)"
    )
    typer.echo(f"package: {result['build']['package_path']}")


if __name__ == "__main__":
    app()
