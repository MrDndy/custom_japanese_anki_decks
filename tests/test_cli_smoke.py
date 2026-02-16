from typer.testing import CliRunner
from jp_anki_builder.cli import app


def test_cli_shows_help():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "scan" in result.output
    assert "review" in result.output
    assert "build" in result.output
