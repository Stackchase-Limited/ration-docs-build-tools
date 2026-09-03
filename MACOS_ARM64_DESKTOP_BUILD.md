# Native macOS Apple Silicon Desktop Build

This is the primary local verification path for Ration Docs Desktop. It builds
a native Apple Silicon application on an ARM64 Mac rather than cross-compiling
or using a Linux container.

## Prerequisites

- Apple Silicon Mac with full Xcode installed and selected
- Python 3, Node.js/npm, Java, CMake, Git, and GNU Make
- `grunt-cli` available on `PATH` (`npm install -g grunt-cli`)
- Sufficient free storage for the source tree, dependencies, and build output

## Stock 9.4 verification build

Run from the root of this repository:

```bash
./tools/mac/build-desktop-arm64.sh
```

The wrapper deliberately asks the build coordinator for
`release/v9.4.0`; it must not use the Ration superproject branch. It configures
the `mac_arm64` platform, which uses native Apple Silicon settings.

The resulting application is intended for local launch and functional checks
before any Ration branding is added. A distributable DMG requires a later
packaging and signing/notarization step.

## Ration release build

After stock verification, fork `desktop-apps`, apply the deliberately small
Ration name/icon/package/legal change set there, repoint only that submodule,
and rebuild with this same native macOS ARM64 path.
