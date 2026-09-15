# Native ARM64 Desktop Build

Ration Docs Desktop can be built natively for Ubuntu ARM64. The build tooling
supports the `linux_arm64` target and supplies ARM64 Qt and sysroot inputs.

## Requirements

- Ubuntu 24.04 ARM64 with Docker
- At least 8 GB RAM and 4 GB swap
- At least 100 GB of free storage available to Docker

## Status: first bring-up attempted 2026-09-15

Attempted natively on Ubuntu 24.04.5 aarch64 (2 cores, 3.9 GB RAM + 7.3 GB swap,
39 GB disk). Driving `build_tools/make.py` with `platform="linux_arm64"` and
`qt-dir="/usr"` - the approach this document suggested but nobody had tried.

**Two blockers found and fixed**, both in our own tooling, both committed:

1. `qt_setup()` recognised a single-prefix Qt only on macOS. It was added for
   Homebrew and gated on `host_platform() == "mac"`; Ubuntu's system Qt has the
   same shape (`/usr/bin/qmake`), so linux_arm64 fell through to logic expecting
   `gcc_64/` subdirectories and printed **"THIS PLATFORM IS NOT SUPPORTED"** once
   per module. That message is misleading - `check_support_platform()` only tests
   whether `<qt_dir>/bin/qmake` exists, so the platform was rejected purely
   because the Qt layout was unrecognised. Now tests the layout, not the host.

2. `check_python()` downloads `tools/linux/python3` and prepends it to `PATH` for
   any Linux host. That bundle is an **x86-64 ELF binary**, so on aarch64 every
   later `python3` fails - ICU's configure reports *"cannot execute binary file:
   Exec format error"*, which reads like a corrupt download. ARM hosts now keep
   their system `python3`. `check_tools()` immediately below already made this
   distinction with `is_os_arm()`.

**Current blocker: ICU.** The build now reaches dependency compilation and fails
building ICU's data library:

    Error generating library file. Failed command: gcc ... -shared -Wl,-Bsymbolic
      -nodefaultlibs -nostdlib -o ../lib/libicudata.so.74.2 ./out/tmp/icudt74l_dat.o
    Error generating assembly code for data.
    make[1]: *** [Makefile:176: packagedata] Error 1

Worth knowing before picking this up: `icu.py` does anticipate a native ARM host -
its cross-compile block is guarded by `not base.is_os_arm()` and is correctly
skipped. The failure is in the *native* build, which writes into a directory named
`linux_64` regardless of host architecture. The likely direction is ICU's data
packaging mode (`pkgdata` assembly generation) rather than anything in our code.

**Also required on a bare Ubuntu box**, beyond the package list below: `p7zip-full`
(the build calls `7z`; without it you get `Error (7z): 127`, which is a
command-not-found in disguise).

**Network note.** Sustained throughput from that box to `github.com` raw content
measured ~70 KB/s, against 1.2 MB/s to other hosts and 3.9 MB/s for the same URL
from a Mac on the same network. A 26 MB dependency took ~7 minutes. Staging the
file by hand does not help - `check_python()` re-downloads it. Worth resolving
before a full run, since the dependency set is far larger.

## Stock 9.4 verification build

> **The Docker path below is not runnable as written, and has not been verified.**
> `tools/linux/build-desktop-arm64-docker.sh` has never existed in this
> repository, and neither has the `automate.py` it is said to invoke. Treat the
> commands below as a description of intent, not instructions.
>
> For a build that does work today, see `MACOS_ARM64_DESKTOP_BUILD.md`, which
> drives `build_tools/make.py` directly. The same approach should port to
> `linux_arm64` by setting `platform` in `build_tools/config`, but that has not
> been tried.

From the root of this repository, run:

```bash
./tools/linux/build-desktop-arm64-docker.sh   # missing - see note above
```

The wrapper was intended to build a native `linux/arm64` Ubuntu image and
invoke:

```bash
python3 ./automate.py desktop --branch=release/v9.4.0   # missing
```

It intentionally uses the upstream release branch, not `ration/9.4`: the
automation coordinates several ONLYOFFICE component repositories, which do not
contain the Ration superproject branch.

Artifacts are retained in `out/`; the expected platform directory is
`out/linux_arm64/`.

## First branded build

After the stock verification succeeds, fork only `desktop-apps`, move its
submodule URL and pinned SHA to the Ration fork, and re-run this same command.
Do not change the `core`, `sdkjs`, `web-apps`, or `desktop-sdk` sources unless
there is a deliberate downstream change to that component.
