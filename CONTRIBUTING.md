# Contributing

## Setup

Dependencies:

- [uv](https://docs.astral.sh/uv/)
- [Just](https://github.com/casey/just) (task runner)
- [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version) (for release workflow)
- [conventional-changelog](https://github.com/conventional-changelog/conventional-changelog)
- [VLC](https://www.videolan.org/)
- (Optional)[Deno JS Runtime](https://github.com/yt-dlp/yt-dlp/wiki/EJS)

## Dev install & run

```bash
git clone https://github.com/vzhd1701/gridplayer.git
cd gridplayer
uv sync
uv run gridplayer
```

## Local build on Windows

Install dependencies:

```bash
choco install zip innosetup
```

Build:

```bash
just build-win-package
```

## Local build on MacOS

Install dependencies:

```bash
./scripts/macos/_init_local_env.sh
```

Build the native Apple Silicon package:

```bash
just build-macos-package-arm64
```

The default macOS build target is `arm64`. If you need an Intel build, run the same
scripts from a native `x86_64` Python environment with `BUILD_MACOS_ARCH=x86_64`.

## Local build on Ubuntu

Install dependencies:

```bash
sudo apt install appstream-util
```

When new resources are added, the compiled resources inside `gridplayer/resources` need to be updated

```bash
sudo apt install qttools5-dev-tools		# for lrelease
just generate-resources
```

Build:

```bash
just build-linux-appimage
```

## Changelog

A pull request that changes what a user sees or does adds its entry to
`CHANGELOG.md` itself, under `## [Unreleased]`, in the section it belongs to
(`Added`, `Changed` or `Fixed`), at the top. Use [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format,
and link the pull request rather than a commit, since a commit's hash can
change when it is merged:

```markdown
- Add multiple A-B loops, played one after another ([#2](https://github.com/nomayooo/gridplayer/pull/2))
```

Tests, refactors, build changes and reverts need no entry. A fix to something
not released yet goes into that feature's entry, not one of its own.

## Release

1. Check that every change is listed under `## [Unreleased]` in `CHANGELOG.md`. Pull requests add their own entries (see Changelog above).

As a guide, print changes from recent commits:

```bash
just changelog       # only important changes
just changelog-all   # full changelog
```

2. See what will be changed:

```bash
commit-and-tag-version --dry-run
```

3. Commit and create release tag:

```bash
commit-and-tag-version
```
