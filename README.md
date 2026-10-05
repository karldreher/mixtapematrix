<center><img src="logo.webp" alt="drawing" width="300"/></center>


~an idea worth tens of dollars total~

~it's like the 80s, but for the 2020s~

~what on earth is music streaming~

Declarative MP3 File Management for passionate listeners.


# Overview

What if you could *copy a file*?

Yes, this has been invented a *long* time ago.

File copying gets so boring.  You have to go and *pick* which file you want to copy, without thinking about *what kinds of files* you might copy.  

**Mixtape Matrix** bridges this gap.  It's desired-state config for MP3 files.  When 2005 finds out about this....  It's going to be *huge*.


# Installation and Usage

`uv tool install` is recommended for install.  

```
uv tool install git+https://github.com/karldreher/mixtapematrix.git
```

Once installed, you need to generate a *config file*.  

```yaml
matrix:
  # absolute paths always appreciated, relative paths supported
  - source_path: ./my-music
    # don't copy these folders (or files)
    exclude_paths:
      - ./my-music/Podcasts
      - "./my-music/Huey Luis"
    destination_path: /example/destination/path
    mp3_files: 
      # all funk, except tracks by one artist or from one album
      - genre: funk
        exclude:
          artist: Artist B
          album: Album Name 2
      - artist: "Fear Factory"
```

You can create a default config file with `mixtape init`.  This also writes `matrix.schema.json` next to it, and the config references it with a `# yaml-language-server: $schema=./matrix.schema.json` comment.  With the [Red Hat YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) installed, VS Code then highlights errors and offers completions and type hints for the config.  Pass `--no-json-schema` to skip the schema file and the comment, and `--force` to overwrite an existing `matrix.yaml`.

Based on the config file, Mixtape Matrix will find any files in `source_path`, which match the directives in `mp3_files`.  If you want to keep funk and Fear Factory in your mixtape, the config file above is half-done for you!

## Excluding files

Two options leave files out, and they work at different levels:

- `exclude_paths` (per matrix) works on **locations**. Each entry is a directory or file, and everything beneath it is skipped without being read. A plain entry matches whole path components, so `rock` never excludes `Crockett`, and relative paths work however `source_path` is written. Plain entries must exist. An entry may end in `**` to match by prefix: `/music/rock**` skips everything whose path starts with `/music/rock` (including `rockabilly`), and `/music/rock/**` skips everything beneath `/music/rock`. `**` is only supported at the end of an entry, and glob entries need not exist.
- `exclude:` (inside an `mp3_files` entry) works on **tags**. It takes the same keys as an entry (`artist`, `album`, `genre`, `album_artist`, and a nested `exclude`). Any tag may be used, whichever tag the entry itself lists.

Excludes are applied in order, path first and then tag:

1. **Path:** a file under an `exclude_paths` entry is dropped for the whole matrix. No `mp3_files` entry can bring it back, whatever its tags say. Use this to keep something out for good, such as a `Huey Luis` folder whose tracks would otherwise be caught by `genre: pop`.
2. **Tag:** each remaining file is tested against every `mp3_files` entry. An entry or `exclude:` block matches when **any** tag it lists matches (case-insensitive). An entry's `exclude:` only carves exceptions out of that entry, so one entry's exception never removes a file another entry matches.

A file is copied when it matches at least one entry and no exclude applies (by path or by tag). An entry needs at least one tag of its own, so "everything except X" is not supported.

`exclude:` is applied to cached tags, so adding or changing one never invalidates the tag cache.

## Run the tool

```
mixtape run
# Or, the long form "mixtapematrix run"
# Use --config to point at a file other than ./matrix.yaml
# Running with no subcommand prints help and exits 1.
# Use --no-cache to ignore the tag cache for one run.
# Use --prune to delete destination files that no matrix copied (off by default).
```
After running, this will send the files from `source_path` to `destination_path` accordingly.

Running a second `mixtape` command while one is active prints a warning and carries on. Concurrent runs are discouraged, since they can overwrite each other's cache. Detection is held in memory by the OS, scoped to your user, and creates no files: on macOS and Linux it is a kernel lock on your home directory, and on Windows a named mutex. It is released automatically if a run is killed, so it cannot go stale.

## List tags

See which values exist in your library before writing `mp3_files` entries:

```
mixtape list tag artist
mixtape list tag genre
# Also: album, album_artist
# Narrow with --artist, --album, --genre, --album-artist (exact, case-insensitive; all must match):
mixtape list tag album --artist Alpha
mixtape list tag artist --genre funk --album-artist Alpha
# Prints the distinct values from every matrix source, one per line, sorted and case-insensitive.
# Use --config to point at a file other than ./matrix.yaml
# Use --no-cache to ignore the tag cache for one run.
```

`list tag` ignores `mp3_files` and reads from the same tag cache as `run`: valid entries are reused and anything missing is discovered and cached for the next run.

## Describe the library as a tree

`describe tag` shows the same library as `list tag`, with more detail: an artist > album > song tree. The shape never changes. Songs are file names without `.mp3`. `FIELD` decides what the tree is narrowed or split by:

| `FIELD` | Is a level of the tree? | `describe tag FIELD` | `describe tag FIELD VALUE` |
| --- | --- | --- | --- |
| `artist`, `album` | yes | the whole tree | only the branches where `FIELD` matches `VALUE` |
| `genre`, `album_artist` | no | one section per `FIELD` value, headed by that value, each holding its own tree | only that section |

```
mixtape describe tag artist Alpha
Alpha
├── First
│   ├── one
│   └── two
└── Third
    └── three

mixtape describe tag genre
Funk
├── Alpha
│   └── First
│       ├── one
│       └── two
└── Beta
    └── First
        └── four
Metal
└── Alpha
    └── Third
        └── three
```

- Matching is exact and case-insensitive, like `mp3_files`. The `--artist`, `--album`, `--genre` and `--album-artist` filters work as in `list tag` and narrow which files are described.
- Names that differ only by case share one node and use the spelling that sorts first.
- A missing artist or album shows as `(unknown artist)` or `(unknown album)`. Files with no ID3 tag are skipped.
- Like `list tag`, it ignores `mp3_files` and uses the tag cache. `--config`, `--no-cache`, `--verbose` and `--debug` are available.

## Speed up repeat runs with a tag cache

Reading the ID3 tag of every MP3 is the slow part of a run. Add a `cache` block to cache the discovered tags between runs:

```yaml
cache:
  ttl: 2d
matrix:
  - source_path: ./my-music
    ...
```

`ttl` is a whole number followed by one unit: `m` (minutes), `h` (hours), `d` (days), `w` (weeks), or `mo` (months, fixed at 30 days). Examples: `30m`, `12h`, `2d`, `1w`, `1mo`. Without a `cache` block, nothing is cached.

- **What is cached:** the artist, album, genre and album artist of every MP3 under `source_path`, so changing the `mp3_files` entries never needs a cache reset. A file whose modification time changed is re-read, new files are added, and deleted files are dropped.
- **Expiry:** the first run after `ttl` has passed deletes the cache and rescans the whole library.
- **The cache belongs to the config file:** each cache is keyed by the config file's path and the `source_path`, so two config files never share or overwrite a cache. Moving or renaming a config file starts a new cache, and the old one is left behind until you clean it up.
- **Where it lives:** `$XDG_CACHE_HOME/mixtapematrix/` (`~/.cache/mixtapematrix/` by default), never next to your config or music. The files are compressed and small: roughly 27 bytes per track, so a 5,000-track library takes about 150 KiB.

Clean up with `mixtape cache clean`, which removes expired caches, caches whose config file or source path no longer exists, and unreadable ones. Use `mixtape cache clean --all` to remove every cache.
