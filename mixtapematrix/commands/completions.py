import click

SHELLS = ("bash", "zsh", "fish")

# The instructions are the ones in Click's shell completion docs:
# https://click.palletsprojects.com/en/stable/shell-completion/
EVAL_FILE = {
    "bash": "~/.bashrc",
    "zsh": "~/.zshrc",
    "fish": "~/.config/fish/completions/{prog}.fish",
}


def _instructions(shell: str, prog: str, var: str) -> str:
    source = f"{var}={shell}_source {prog}"
    eval_file = EVAL_FILE[shell].format(prog=prog)
    if shell == "fish":
        run = f"{source} | source"
        save = f"{source} > ~/.config/fish/completions/{prog}.fish"
        sourcing = ""
    else:
        run = f'eval "$({source})"'
        script = f"~/.{prog}-complete.{shell}"
        save = f"{source} > {script}"
        sourcing = f"\n\nSource the file in {eval_file}:\n\n  . {script}"
    return (
        f"{shell}\n\n"
        f"Add this to {eval_file}:\n\n  {run}\n\n"
        f"Using eval runs {prog} every time a shell starts, which can delay shell "
        f"responsiveness. To speed it up, save the script to a file instead:\n\n"
        f"  {save}{sourcing}"
    )


@click.command(name="completions")
@click.option("--bash", "shells", flag_value="bash", multiple=True, help="Bash only")
@click.option("--zsh", "shells", flag_value="zsh", multiple=True, help="Zsh only")
@click.option("--fish", "shells", flag_value="fish", multiple=True, help="Fish only")
@click.pass_context
def completions(ctx, shells):
    """Show how to enable tab completion in your shell.

    Prints the setup instructions for bash, zsh and fish, or only for the shells
    given as options. Start a new shell after changing your shell's startup file.

    \b
    mixtape completions
    mixtape completions --zsh
    """
    prog = ctx.find_root().info_name
    var = f"_{prog}_COMPLETE".replace("-", "_").upper()
    chosen = [s for s in SHELLS if s in shells] or SHELLS
    click.echo("\n\n".join(_instructions(s, prog, var) for s in chosen))
