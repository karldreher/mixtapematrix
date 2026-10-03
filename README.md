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
    # don't copy the Huey Luis folder
    exclude_path: "./my-music/Huey Luis"
    destination_path: /example/destination/path
    mp3_files: 
      - genre: funk
      - artist: "Fear Factory"
```

You can create a default config file with `mmatrix init`.  This also writes `matrix.schema.json` next to it, and the config references it with a `# yaml-language-server: $schema=./matrix.schema.json` comment.  With the [Red Hat YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) installed, VS Code then highlights errors and offers completions and type hints for the config.  Pass `--no-json-schema` to skip the schema file and the comment, and `--force` to overwrite an existing `matrix.yaml`.

Based on the config file, Mixtape Matrix will find any files in `source_path`, which match the directives in `mp3_files`.  If you want to keep funk and Fear Factory in your mixtape, the config file above is half-done for you!

## Run the tool

```
mixtapematrix run
# Or, the handy "mmatrix run"
# Use --config to point at a file other than ./matrix.yaml
# Running with no subcommand prints help and exits 1.
# Use --no-cache to ignore the tag cache for one run.
# Use --prune to delete destination files that no matrix copied (off by default).
```
After running, this will send the files from `source_path` to `destination_path` accordingly.

Running a second `mmatrix` command while one is active prints a warning and carries on. Concurrent runs are discouraged, since they can overwrite each other's cache. Detection is held in memory by the OS, scoped to your user, and creates no files: on macOS and Linux it is a kernel lock on your home directory, and on Windows a named mutex. It is released automatically if a run is killed, so it cannot go stale.

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

Clean up with `mmatrix cache clean`, which removes expired caches, caches whose config file or source path no longer exists, and unreadable ones. Use `mmatrix cache clean --all` to remove every cache.
