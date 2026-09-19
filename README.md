# Ration Docs - build_tools

The build: fetches and compiles the third-party dependencies, builds every component in order, and assembles the payload the applications ship.

Part of **[Ration Docs Desktop](https://github.com/Stackchase-Limited/ration-docs-desktop)**, an offline office suite maintained by Stackchase Limited. This repository is a modified version of [ONLYOFFICE/build_tools](https://github.com/ONLYOFFICE/build_tools), originally developed by Ascensio System SIA, forked at release 9.4.0.

## What lives here

`configure.py` writes the build configuration, `make.py` runs the build, and
`scripts/core_common/modules/` holds one module per dependency - v8, CEF, ICU,
boost, OpenSSL, hunspell and the rest.

`ARM64_DESKTOP_BUILD.md` documents the Linux arm64 build in detail: the packages
the machine needs, and the failures that do not say what they mean.

## Using it

    git clone --recursive https://github.com/Stackchase-Limited/ration-docs-desktop.git
    cd ration-docs-desktop/build_tools
    python3 configure.py --module desktop --platform linux_arm64 --qt-dir /usr
    python3 make.py

Expect a long first build: v8, CEF, ICU, boost and OpenSSL are all compiled from
source before any of our code is reached.

| | Minimum |
|---|---|
| Disk | 100 GB |
| RAM | 8 GB, plus swap |
| CPU | more cores is the difference between hours and many hours |
| Python | 3, with a working `python3` on PATH |

Verified on macOS (Apple Silicon) and Ubuntu 24.04 arm64. The x86-64 paths are
upstream's and are untouched, but this fork has not built them.

## Licence and attribution

Distributed under the **GNU Affero General Public License v3** together with the
additional terms supplied with the original program; both are in `LICENSE`.
Non-code elements - illustrations, icon sets, documentation - are **CC BY-SA 4.0**.

    Copyright (C) Ascensio System SIA, 2009-2026
    Copyright (C) Stackchase Limited, 2026

This is a modified version of ONLYOFFICE software. The original was developed by
Ascensio System SIA; modifications are by Stackchase Limited, 2026. **ONLYOFFICE is
a trademark of Ascensio System SIA**, used here only to identify the software this
is based on. Ration Docs is not produced by, endorsed by, or affiliated with
Ascensio System SIA, and no trademark rights are granted by the licence.

The corresponding source for a released binary is the superproject at the matching
tag, with this repository at the commit that tag records.
