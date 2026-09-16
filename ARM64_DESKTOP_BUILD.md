# Native ARM64 Desktop Build

Ration Docs Desktop can be built natively for Ubuntu ARM64. The build tooling
supports the `linux_arm64` target and supplies ARM64 Qt and sysroot inputs.

## Requirements

- Ubuntu 24.04 ARM64 with Docker
- At least 8 GB RAM and 4 GB swap
- At least 100 GB of free storage available to Docker

## Status: builds and runs, 2026-09-16

Ubuntu 24.04.5 aarch64, 6 cores, 7.6 GB RAM, 78 GB disk. `build_tools/make.py`
with `platform="linux_arm64"`, `qt-dir="/usr"`, `sysroot="0"` completes, and the
result starts.

What that took, in the order the build hit them. Every one of these is committed;
the point of listing them is that **not one error named its own cause**.

*Our tooling assumed an x86 host, four times over.* v8's DEPS pulls an x86-64
python bundle, an x86-64 rustc, an x86-64 clang and - because it names the CIPD
package by architecture rather than with `${platform}` - an x86-64 `gn`. Each
appears as `Exec format error` on a different file, several steps from anything
that mentions architecture. `file(1)` on the binary settles each one in seconds.

*Markers standing in for the state they describe*, four more times: the v8 branch
pin ran only on the first fetch (so the tree sat on **trunk 15.6** calling itself
v8_89, which is why ninja was passing clang flags no released compiler has); the
jinja2 patch was guarded by a `.bak` that outlived the file; hunspell skipped its
clone because a directory existed without a `.git`; boost skipped its module
builds because `b2 headers install` had created the output directory. Each now
checks the artifact - the checkout's HEAD, the file's contents, the clone's
`.git`, a library the build is supposed to produce.

*A bare `python`.* 8.9-era chromium scripts, gn's default `exec_script`
interpreter, and twelve call sites in `build_tools` all invoke `python`, which no
distro has shipped since 20.04. `Error (env): 127` is command-not-found in
disguise.

*2021 sources against a 2024 toolchain.* libstdc++ 13 stopped including
`<cstdint>` transitively, and clang 16 made `-Wenum-constexpr-conversion` an
error; both are handled in `v8_89.py` by patching v8's `config("compiler")`,
since that tree has no `extra_cflags` gn arg to hang them on.

*ICU built correctly under the wrong name.* On aarch64 the "cross_build" is the
native build but is published as `linux_64`, and the cross-compile branch is
then skipped because there is nothing to cross-compile - so the first link fails
with `cannot find .../icu/linux_arm64/build/libicuuc.so.74` while that library
sits one directory over, `file(1)` reporting "ARM aarch64".

*Qt 5.15 and glib against code written for neither.* Qt's `signals` macro
collides with `GDBusSignalInfo **signals` in gio's headers (fixed by
`platform_linux/glib_includes.h`, which suppresses the keyword across the glib
includes); `<QPainterPath>` stopped arriving with `<QPainter>` in 5.13; and
`<QDesktopWidget>` was included only when `QT_VERSION < 5.11`, which is exactly
backwards.

*Two of our own fixes had never been compiled.* macOS builds `desktop-apps/macos`
and never touches `win-linux/`, so the Wayland guard (#2105) called
`Utils::isWaylandSession()` when the function is in `WindowHelper`, and the
relative-hyperlink fix called `GetLocalFilePath()` on a `CCefView` when it belongs
to `CCefViewEditor`. Neither could ever have built. **Treat any win-linux change
made on a Mac as unverified until this box has compiled it.**

*Static libstdc++ in a shared library.* `-static-libstdc++` was applied to every
app and plugin target. On a shared library it takes the libstdc++.a members that
reference the runtime's private statics without the ones that define them, and
`libstdc++.so.6` exports no private statics - so the payload built, packaged,
passed our symbol-closure check, and then died before `main()`:

    ./DesktopEditors: symbol lookup error: .../libascdocumentscore.so:
    undefined symbol: _ZNSt8ios_base4Init20_S_synced_with_stdioE

Static libstdc++ is opt-in now (`CONFIG += core_linux_static_libstd`) on both
sides, and `check_symbol_closure.py` gained a `check_runtime()` pass that asks the
real loader, via `ldd -r`, to resolve every relocation. It reports all ten
symbols on the payload that shipped without them.

### Verified on the box

- `make.py` exits 0; `out/linux_arm64/onlyoffice/desktopeditors` is 1.9 GB.
- `ldd -r` on the payload: no undefined symbols. `check_symbol_closure.py`: ok.
- `DesktopEditors` starts and prints its usage under `QT_QPA_PLATFORM=offscreen`.
- x2t round trip: `csv -> xlsx` (4,744 bytes) and `xlsx -> pdf` (13,823 bytes,
  `%PDF-1.7`), which exercises x2t, doctrenderer, v8, sdkjs and the font stack.
  `AllFonts.js` has to exist first - `allfontsgen` generates it, and packaging is
  what normally does so.

### Not done

The Linux app still carries ONLYOFFICE identity: `APP_TITLE`, `APP_DATA_PATH`,
`WINDOW_NAME` and the help/release URLs in `win-linux/src/defines.h`, plus the
package name, `.desktop` files and icons under `desktop-apps/package`. macOS was
renamed in e829d0d7d; Linux has had no equivalent. **No Linux artifact should be
published until it has one** - see `REQUIRES_APPROVAL.md`.

### Machine state, not code - redo this if the VM is rebuilt

These live on the box rather than in this repository, and all were needed before
a build could get anywhere.

**Packages.** On top of the list below, installed one failure at a time as the
build asked for them:

    clang lld                      # v8's bundled clang is x86-64
    qtmultimedia5-dev libqt5svg5-dev libqt5x11extras5-dev qttools5-dev
    libx11-xcb-dev libxcb1-dev libxcb-keysyms1-dev libxkbcommon-x11-dev
    libgl1-mesa-dev libglu1-mesa-dev libxext-dev
    libnotify-dev libgtk-3-dev libatk1.0-dev libglib2.0-dev libdbus-1-dev
    libcups2-dev
    npm  +  `npm install -g grunt-cli`   # the JS build shells out to grunt

Each absence shows up as something other than a missing package: a missing Qt
module is `Project ERROR: Unknown module(s) in QT`, a missing header is a
`fatal error` in a source file, and a missing grunt is `Error (grunt): 127`.
`pkg-config --exists` on each of atk, dbus-1, gio-unix-2.0, glib-2.0, gtk+-3.0,
gtk+-unix-print-3.0, libnotify, xcb and xext is the quick way to check the set.


**DNS fallbacks.** The VMware NAT resolver alone is not reliable enough for the
v8 fetch. A ~2GB clone from `chromium.googlesource.com` got past 1GB and then
died with

    fatal: unable to access 'https://chromium.googlesource.com/v8/v8.git/':
    Could not resolve host: chromium.googlesource.com

and gclient moved the half-finished checkout to `_bad_scm`. Resolution was fine
again seconds later, so the NAT resolver simply blips. Fixed by giving
systemd-resolved company, in `/etc/systemd/resolved.conf.d/10-rd-fallback.conf`:

    [Resolve]
    FallbackDNS=1.1.1.1 8.8.8.8 9.9.9.9
    DNS=172.16.84.2 1.1.1.1 8.8.8.8

**Swap, made persistent.** An 8GB swapfile created with `fallocate` + `swapon`
did *not* survive a reboot, because it was never added to `/etc/fstab` - it sat
on disk consuming space while contributing nothing. It is now 4GB and in fstab:

    /swap-rd none swap sw 0 0

**Sizing.** The VM was raised from 2 vCPU / 4GB / 50GB to **6 vCPU / 8GB / 80GB**
before v8 would fit. Note that VMware growing the virtual disk does *not* extend
the guest partition: `growpart /dev/nvme0n1 2 && resize2fs /dev/nvme0n1p2` is
needed inside afterwards, or the extra space is invisible and it looks as though
the resize did nothing.

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
