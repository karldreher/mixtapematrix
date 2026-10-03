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

You can create a default config file with `mmatrix init`.  This also writes `matrix.schema.json` next to it, and the config references it with a `# yaml-language-server: $schema=./matrix.schema.json` comment.  With the [Red Hat YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) installed, VS Code then highlights errors and offers completions and type hints for the config.  Pass `--no-json-schema` to skip the schema file and the comment.

Based on the config file, Mixtape Matrix will find any files in `source_path`, which match the directives in `mp3_files`.  If you want to keep funk and Fear Factory in your mixtape, the config file above is half-done for you!

## Run the tool

```
mixtapematrix run
# Or, the handy "mmatrix run"
# Use --config to point at a file other than ./matrix.yaml
# Running with no subcommand prints help and exits 1.
```
After running, this will send the files from `source_path` to `destination_path` accordingly.
