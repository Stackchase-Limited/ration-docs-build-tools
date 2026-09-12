# Native macOS Apple Silicon Desktop Build

This is the primary local verification path for Ration Docs Desktop. It builds
native Apple Silicon binaries on an ARM64 Mac rather than cross-compiling or
using a Linux container.

Last verified: 2026-09-12, on macOS 24.6.0 / Apple Silicon. The build completed
with no errors.

## Prerequisites

- Apple Silicon Mac with full Xcode installed and selected
  (`xcode-select -p` should print a path inside `Xcode.app`)
- Python 3, Node.js/npm, Java, CMake, Git, and GNU Make
- `grunt-cli` on `PATH` (`npm install -g grunt-cli`)
- Qt 5 at the path named by `qt-dir` in `build_tools/config`
  (currently `/opt/homebrew/opt/qt@5`)
- Sufficient free storage for the source tree, dependencies, and build output.
  Around 140 GB free was comfortable for an incremental build.

The versions this was last verified against: Python 3.13.9, Node 20.12.2,
npm 10.5.0, OpenJDK 24.0.1, CMake 4.1.1, GNU Make 3.81, grunt-cli 1.5.0.

## Build

The build is driven by `build_tools/make.py`, using the checked-in
`build_tools/config`. Run:

```bash
cd build_tools
python3 make.py
```

`build_tools/config` already selects what this path needs:

| Option | Value | Why it matters |
|---|---|---|
| `platform` | `mac_arm64` | native Apple Silicon |
| `module`   | `desktop`   | builds the desktop editors, not the server |
| `update`   | `0`         | **make.py performs no git operations** |
| `qt-dir`   | `/opt/homebrew/opt/qt@5` | must match the installed Qt 5 |

### Do not set `update` to `1` in this repository

With `update="0"`, `make.py` skips `base.update_repositories()` entirely, so it
never fetches or checks out anything. That is what makes it safe to build a
tree that has local work in it.

With `update="1"` it would `git fetch` and `git checkout -f` each component
repository at the `branch` value (`release/v9.4.0`), which would move our
submodules off their `ration/*` branches and discard uncommitted work. The
`branch` setting in `config` is inert while `update` is `0`, and should stay
that way for local verification builds.

## What it produces

Payload under `build_tools/out/mac_arm64/onlyoffice/desktopeditors/`:

- `ascdocumentscore.framework` - the desktop-sdk library (`cefview`,
  `applicationmanager`, `cefapplication`, …)
- `Chromium Embedded Framework.framework`, `hunspell.framework`
- `converter/` - `x2t` and the per-format libraries
- `editors/` - built `sdkjs`, `web-apps`, `sdkjs-plugins`, `webext`
- `dictionaries/`, `fonts/`, `providers/`, `editors_helper*.app`

**This step does not produce a launchable `.app` or a DMG.** The branded macOS
bundle is assembled separately from `desktop-apps/macos` (see
`ONLYOFFICE.xcodeproj` there, and `build_tools/make_package.py`); signing and
notarization are later steps again. Neither is covered by this document.

## Checking that a change actually got built

Header changes in `desktop-sdk` recompile several translation units, so it is
worth confirming rather than assuming:

```bash
# which objects were rebuilt
grep -oE '\-o [a-zA-Z0-9_/.]*\.o\b' build.log | awk '{print $2}' | xargs -n1 basename | sort -u

# no errors anywhere
grep -nE 'error:|fatal error|\*\*\* \[' build.log
```

To confirm a change reached the shipped binary, look for a string literal the
change introduced:

```bash
strings -a .../ascdocumentscore.framework/Versions/A/ascdocumentscore | grep -F -- '<new literal>'
```

To exercise the built editor code without assembling an app, drop the new
`sdkjs` into an existing bundle with `harness/bin/inject-sdkjs.sh`, or convert
documents directly with `harness/bin/x2t.sh`. See `harness/README.md`.

## Ration release build

After a stock verification build, apply the deliberately small Ration
name/icon/package/legal change set in `desktop-apps`, repoint only that
submodule, and rebuild through this same path. Leave `core`, `sdkjs`,
`web-apps` and `desktop-sdk` alone unless there is a deliberate downstream
change to that component.
