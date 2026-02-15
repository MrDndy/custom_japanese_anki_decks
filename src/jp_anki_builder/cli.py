import typer

app = typer.Typer()


@app.command()
def scan() -> None:
    """Scan screenshots and produce OCR/candidate artifacts."""


@app.command()
def review() -> None:
    """Review and approve candidate words."""


@app.command()
def build() -> None:
    """Build Anki package from approved words."""


@app.command()
def run() -> None:
    """Run scan -> review -> build."""
