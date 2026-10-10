import click
from pydantic import ValidationError

from mixtapematrix.commands.cache import cache_group
from mixtapematrix.commands.completions import completions
from mixtapematrix.commands.describe import describe_group
from mixtapematrix.commands.list import list_group
from mixtapematrix.commands.run import init, run
from mixtapematrix.service import MixtapeMatrix

__all__ = ["MixtapeMatrix", "cli"]


class MixtapeGroup(click.Group):
    def invoke(self, ctx: click.Context):
        """Report an invalid config as a one-line error instead of a traceback."""
        try:
            return super().invoke(ctx)
        except ValidationError as e:
            problems = []
            for error in e.errors():
                message = error["msg"].removeprefix("Value error, ")
                where = ".".join(map(str, error["loc"]))
                problems.append(f"{where}: {message}" if where else message)
            raise click.ClickException(
                f"Invalid config: {'; '.join(problems)}"
            ) from None


@click.group(cls=MixtapeGroup, invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Copy and transform music files according to a matrix YAML config."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(1)


cli.add_command(cache_group)
cli.add_command(describe_group)
cli.add_command(list_group)
cli.add_command(run)
cli.add_command(init)
cli.add_command(completions)
