import pytest
from click.testing import CliRunner

from mixtapematrix.main import cli

SHELLS = ["bash", "zsh", "fish"]


def completions_output(*args, prog_name="mixtape"):
    result = CliRunner().invoke(cli, ["completions", *args], prog_name=prog_name)
    assert result.exit_code == 0, result.output
    return result.output


def test_without_a_flag_every_shell_is_shown():
    output = completions_output()
    for shell in SHELLS:
        assert f"_MIXTAPE_COMPLETE={shell}_source mixtape" in output


@pytest.mark.parametrize("shell", SHELLS)
def test_a_flag_shows_only_that_shell(shell):
    output = completions_output(f"--{shell}")
    assert f"_MIXTAPE_COMPLETE={shell}_source" in output
    for other in set(SHELLS) - {shell}:
        assert f"{other}_source" not in output


def test_flags_combine():
    output = completions_output("--bash", "--fish")
    assert "bash_source" in output
    assert "fish_source" in output
    assert "zsh_source" not in output


def test_instructions_use_the_invoked_command_name():
    output = completions_output("--zsh", prog_name="mixtapematrix")
    assert "_MIXTAPEMATRIX_COMPLETE=zsh_source mixtapematrix" in output
    assert "_MIXTAPE_COMPLETE" not in output
    assert "~/.mixtapematrix-complete.zsh" in output


def test_config_completes_file_paths():
    env = {
        "_MIXTAPE_COMPLETE": "bash_complete",
        "COMP_WORDS": "mixtape run --config ",
        "COMP_CWORD": "3",
    }
    result = CliRunner().invoke(cli, [], prog_name="mixtape", env=env)
    assert result.stdout == "file,\n"
