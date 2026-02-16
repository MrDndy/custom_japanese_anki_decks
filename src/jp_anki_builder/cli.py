from __future__ import annotations

import typer

from jp_anki_builder.pipeline import Pipeline

app = typer.Typer()


@app.command()
def scan(
    images: str = typer.Option(..., help="Image file or directory path."),
    source: str = typer.Option(..., help="Top-level source id, e.g. game or manga name."),
    run_id: str = typer.Option(..., help="Unique run id, e.g. mangaa-ch01."),
    data_dir: str = typer.Option("data", help="Data storage directory."),
    ocr_mode: str = typer.Option("tesseract", help="OCR backend: tesseract or sidecar."),
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
    save_excluded_to_known: bool = typer.Option(
        False,
        "--save-excluded-to-known",
        help="Append manually excluded words to known_words.txt.",
    ),
) -> None:
    """Review and approve candidate words."""
    result = Pipeline(data_dir=data_dir).review(
        source=source,
        run_id=run_id,
        exclude=exclude,
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
) -> None:
    """Build Anki package from approved words."""
    try:
        result = Pipeline(data_dir=data_dir).build(
            source=source,
            run_id=run_id,
            volume=volume,
            chapter=chapter,
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
    ocr_mode: str = typer.Option("tesseract", help="OCR backend: tesseract or sidecar."),
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
