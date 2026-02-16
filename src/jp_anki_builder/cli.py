import typer

from jp_anki_builder.pipeline import Pipeline

app = typer.Typer()


@app.command()
def scan() -> None:
    """Scan screenshots and produce OCR/candidate artifacts."""
    Pipeline().scan()


@app.command()
def review() -> None:
    """Review and approve candidate words."""
    Pipeline().review()


@app.command()
def build() -> None:
    """Build Anki package from approved words."""
    Pipeline().build()


@app.command()
def run() -> None:
    """Run scan -> review -> build."""
    Pipeline().run_all()


if __name__ == "__main__":
    app()
