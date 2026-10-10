import click

from mixtapematrix.cache import clean_cache, list_cache
from mixtapematrix.lock import locked


def _format_bytes(size: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


@click.group(name="cache")
def cache_group():
    """Manage the tag cache."""


@cache_group.command(name="list")
def list_command():
    """List tag caches with their status, size, source path and config file."""
    caches = list_cache()
    for item in caches:
        line = f"{item.name}  {item.status}  {_format_bytes(item.size)}"
        if item.header:
            line += f"  {item.header.source_root}  (config: {item.header.config_path})"
        click.echo(line)
    if not caches:
        click.echo("No cache files")


@cache_group.command()
@click.option(
    "--all", "all_files", is_flag=True, help="Delete every cache file, not only stale"
)
@locked
def clean(all_files):
    """Delete stale tag caches (expired, orphaned, or unreadable)."""
    removed = clean_cache(all_files=all_files)
    for item in removed:
        click.echo(f"Removed {item.name} ({item.reason}, {_format_bytes(item.size)})")
    freed = _format_bytes(sum(item.size for item in removed))
    click.echo(f"Removed {len(removed)} cache file(s), freed {freed}")
