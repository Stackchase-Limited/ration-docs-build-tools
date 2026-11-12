# Linux x86-64 Desktop Build (.deb)

Builds the Ration Docs desktop editors for `linux_64` with `build_tools/make.py`, entirely inside a
Docker container, and packages `ration-docs_<version>-<build>_amd64.deb`. Nothing is installed on the
host; the host needs only Docker (user in the `docker` group, no sudo).

## Status: builds, installs and runs, 2026-11-12

| | |
|---|---|
| Host | Ubuntu 22.04 x86_64, 4 cores, 7.5 GB RAM, ~1.9 GB host swap, Docker |
| Build image | `ubuntu:24.04` + packages below + Qt 5.15.2 `gcc_64` (aqtinstall) |
| Sources | superproject `ration/9.4-stability` 3248422 pins; build_tools 235d1e9 (+ 2911445, below) |
| Artefact | `ration-docs_2026.2.0-1_amd64.deb`, 408,974,736 bytes, Installed-Size 1.41 GB |
| Verified | apt-installs into a clean `ubuntu:24.04` container; starts on Xvfb; opens/edits/saves docx, xlsx, pptx, pdf |

The binaries need glibc 2.39 / libstdc++ 13 (built on 24.04 without a sysroot), so this .deb installs on
Ubuntu 24.04+ / Debian 13+, not on 22.04. A 22.04-installable package needs the upstream route
(`sysroot="1"`, the ubuntu16 sysroot with its gcc 5) or a 22.04 build image; neither has been tried.

## Sources

`update="0"`: make.py does no git operations, so the tree must be complete. Copy each repository at its
pin with `git archive` (no history is needed; nothing in the desktop build calls git on these trees):

| Directory | Commit |
|---|---|
| core | ccddc3317b520a04016d782bba7b33333b0c5aef |
| sdkjs | 80e0954ad1c2366ffb7b1112fd8a3c568ca1335e |
| web-apps | b1ddc7a26020a3cf97a3b32d0cb234f6dace71da |
| desktop-sdk | bdbd5c35081b4925ce53d1c597a1b9947af0756e |
| desktop-apps | 5d2068709b9016910515b856c0ae518b2c7e761f |
| dictionaries | 27dae489274eea48ab3001a2e6da885e8f80fbd4 |
| build_tools | 235d1e9 (Version 2026.2.0) + 2911445 |
| onlyoffice.github.io | 683027f (ration/9.4-stability) |
| core-fonts | 7030c66 (ration/9.4-stability) |
| document-templates | 71430c9 (ration/9.4-stability) |

All ten sit side by side in one directory (make.py finds them as `build_tools/../<name>`).
Over a slow link expect ~45 min for the 3 GB of archives; compress with `gzip -1` in the pipe.

```bash
for p in core:<sha> sdkjs:<sha> ...; do r=${p%%:*}; c=${p#*:}
  git -C $REPO/$r archive --format=tar $c | gzip -1 | ssh box "mkdir -p tree/$r && tar -xz -C tree/$r"
done
```

## Build image (`rd-builder`)

```dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
  sudo python3 python3-pip python-is-python3 tar wget curl git ca-certificates apt-transport-https \
  autoconf2.13 autoconf automake build-essential cmake perl libtool p7zip-full subversion gzip xz-utils bzip2 unzip zip rsync file pkg-config m4 lsb-release \
  libglib2.0-dev libglu1-mesa-dev libgl1-mesa-dev libgtk-3-dev libatk1.0-dev libpulse-dev libasound2-dev libatspi2.0-dev libcups2-dev libdbus-1-dev libicu-dev \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libx11-xcb-dev libxcb1-dev libxcb-keysyms1-dev libxcb-icccm4-dev libxcb-image0-dev libxcb-render-util0-dev \
  libxcb-xinerama0-dev libxcb-xkb-dev libxcb-randr0-dev libxcb-shape0-dev libxcb-xfixes0-dev libxcb-sync-dev libxcb-util-dev libxcb-cursor-dev \
  libxi-dev libxrender-dev libxss1 libncurses6 libxkbcommon-dev libxkbcommon-x11-dev libnotify-dev libxext-dev libfontconfig1-dev libfreetype-dev \
  nodejs npm default-jdk-headless clang lld ninja-build \
  debhelper dpkg-dev fakeroot dh-make \
  && rm -rf /var/lib/apt/lists/*
RUN npm install -g grunt-cli@1.5.0
RUN pip3 install --break-system-packages --no-cache-dir aqtinstall==3.1.21 && aqt install-qt -O /opt/qt linux desktop 5.15.2 gcc_64 && rm -rf /root/.cache
```

3.4 GB, ~25 min to build. The list is build_tools' `tools/linux/deps.py` plus what
ARM64_DESKTOP_BUILD.md found missing, with 24.04 package names (`libxcb*` spelled out).
`clang lld ninja-build` are not used on x86-64 (v8 uses its bundled clang 12) but are harmless.

**Why Qt 5.15.2 from qt.io, not Ubuntu's Qt.** build_tools deploys Qt by copying
`<qt-dir>/gcc_64/{lib,plugins,qml}` into the payload, and the .deb's Depends list no Qt packages, so
the payload must carry Qt. With `qt-dir="/usr"` (the ARM64 recipe) `qt_copy_lib` looks in
`/usr/bin/../lib/libQt5Core.so.5.15.x`, finds nothing, warns, and the payload ships without Qt -
it only runs where the system Qt happens to be installed. The official 5.15.2 binaries have the
expected layout (and their own ICU 56, which `qt_copy_icu` ships). Upstream ships 5.9.9; 5.15 is what
the fork's Qt code has been compiled against (Qt 5.15 fixes in ARM64_DESKTOP_BUILD.md).

## Configuration (`build_tools/config`)

```
module="desktop"
platform="linux_64"
update="0"
clean="1"
qt-dir="/opt/qt/5.15.2"
sysroot="0"
beta="0"
desktop-marketplace="1"
multiprocess="0"
```

`multiprocess="0"` stops qmake.py passing `-j<cpu_count>` to make; the job count then comes from
`MAKEFLAGS` in the container environment (see Memory). `clean="1"` for a from-scratch build;
`clean="0"` to resume after an interruption (it only controls `make clean` before each qmake project).

## Run

```bash
docker run -d --name rd-build --user 1000:1000 --memory 6500m --memory-swap 6500m \
  -e HOME=/rb/home-build -e MAKEFLAGS=-j3 -e PRODUCT_VERSION=2026.2.0 -e BUILD_NUMBER=1 \
  -v $PWD:/rb -w /rb/tree/build_tools rd-builder python3 make.py
docker logs -f rd-build > make.log
```

Run as the host user (files stay deletable without sudo) with a HOME inside the build directory
(npm, vpython and gclient write there; v8_89.py also runs `git config --global` on macOS only).
The memory cap matters on a shared workstation: an OOM then kills the build, not the desktop session.

Then package (7 min):

```bash
docker run --rm --user 1000:1000 -e HOME=/rb/home-build -v $PWD:/rb rd-builder \
  bash -c "cd /rb/tree/desktop-apps/package && make deb PRODUCT_VERSION=2026.2.0 BUILD_NUMBER=1"
# -> tree/desktop-apps/package/deb/ration-docs_2026.2.0-1_amd64.deb (+ .ddeb, .buildinfo, .changes)
```

(build_tools' `make_package.py -P linux_x86_64 -T desktop` would run `make clean && make <targets>` for
two editions; calling `make deb` directly builds the opensource edition only.)

## Timings (4 cores; the first run had to be repeated twice, see Pitfalls)

| Phase | Time |
|---|---|
| boost 1.72 recursive clone (~150 submodules) + build, CEF, ICU, OpenSSL | ~20 min |
| v8 8.9: depot_tools + `fetch v8` (trunk, ~3.5 GB incl. deps) + pin to 8.9 + hooks | ~35 min |
| v8 ninja build (2432 steps, ninja default -j6) | ~35 min |
| other 3rd party (html, iwork, md, hunspell, harfbuzz, hyphen, googletest, brotli, heif) | ~10 min |
| core + desktop-sdk + desktop-apps (qmake, -j3) | ~45 min |
| sdkjs + web-apps + start page (grunt) + deploy | ~15 min |
| `make deb` | 7 min |

Wall clock of the three make.py runs: 56 + 64 + 19 min (the 19 min run resumed with `clean="0"`).
A clean single run should be about 2 h 40 min plus packaging. The tree is 36 GB afterwards.

## Memory

Peak anonymous memory of the build cgroup (sampled every 10 s from `memory.stat`):
- v8 ninja at its default -j6: 1.85 GB.
- core at -j4: **6.41 GB, then OOM-killed** at the 6.5 GB cap, compiling `OdfFile` (each of those
  translation units takes ~1.5 GB with g++ 13 -O2).
- core at -j3 (`MAKEFLAGS=-j3`): 3.67 GB peak. Use -j3 (or -j2) on an 8 GB machine.

No swap file was added: `swapon` needs root on the host, and a privileged container to get it would
amount to the same thing.

## Third-party downloads (all from the build itself; none staged by hand)

- `https://github.com/ONLYOFFICE-data/build_tools_data/raw/refs/heads/master/python/python3.tar.gz` (+ `extract.sh`)
- boost: `https://github.com/boostorg/boost.git` (tag boost-1.72.0, --recursive: ~150 `boostorg/<lib>.git`)
- CEF 109.1.18+gf1c41e4+chromium-109.0.5414.120: `https://github.com/ONLYOFFICE-data/build_tools_data/raw/refs/heads/master/cef/5414/linux_64/cef_binary.7z`
- ICU: `https://github.com/unicode-org/icu.git` (release-74-x)
- OpenSSL: `https://github.com/openssl/openssl.git` (OpenSSL_1_1_1f)
- v8: `https://chromium.googlesource.com/chromium/tools/depot_tools.git`, `https://chromium.googlesource.com/v8/v8.git`
  and its gclient DEPS (chromium.googlesource.com mirrors incl. perfetto, partition_allocator, boringssl,
  icu; `commondatastorage.googleapis.com/chromium-browser-clang/Linux_x64/clang-llvmorg-12-init-16296-g5e476061-1.tgz`;
  debian_sid amd64/i386 sysroots from `commondatastorage.googleapis.com/chrome-linux-sysroot`; GCS test data)
- core/Common/3dParty fetch scripts: harfbuzz, hunspell, hyphen, brotli, md4c, gumbo-parser, katana-parser,
  libetonyek/librevenge/libodfgen/mdds/glm (iwork), googletest, x265 (bitbucket), libde265, libheif
- npm registry (sdkjs, web-apps, start page, plugins); `pypi.org` (aqtinstall); `download.qt.io` mirrors (Qt 5.15.2);
  `archive.ubuntu.com` (apt)

gclient prints "STALL DETECTED ... silent for 5 minutes" during the 2 GB v8 clone and retries
perfetto/partition_allocator once; both are noise. depot_tools also prints
`./cipd: line 146: ./depot_tools/cipd_client_version.digests: No such file or directory` and
"Platform linux-amd64 is not supported by the CIPD client bootstrap" once; the fetch carries on.

## Pitfalls hit, in order

1. **v8 host tools would not link** (run 1, after 56 min):
   `ld.lld: .../llvm-build/Release+Asserts/bin/../lib/libstdc++.so.6: version 'GLIBCXX_3.4.30' not found
   (required by /lib/x86_64-linux-gnu/libicuuc.so.74)`. v8 8.9's bundled clang 12 ships a 2021
   libstdc++.so.6 in its `lib/` and puts that directory on the link path. `fix_ubuntu24()` already swaps
   it for the host's, but only with a sysroot. **Fixed in build_tools 2911445** (branch
   `wip/rd-build-linux-x64`, worktree `.rd-work/wt/dr-build_tools`): the swap also runs without a
   sysroot on non-ARM hosts, and only swaps a real file, so a re-run no longer moves its own symlink.
2. **OOM at -j4** in core's OdfFile (run 2): see Memory. Fixed by configuration (`multiprocess="0"` +
   `MAKEFLAGS=-j3`), no source change.
3. **The .deb installed but did not start** on a clean 24.04:
   `RationDocs: error while loading shared libraries: libnss3.so`. `ldd` over the payload also lists
   libnspr4/libnssutil3/libsmime3 (CEF), libxcb-icccm4/-image0/-keysyms1/-render-util0/-xinerama0
   (Qt's xcb platform plugin) and libpulse-mainloop-glib0 (QtMultimedia). The RPM spec already
   requires the xcb-util set. **Fixed in desktop-apps 7f3406c96** (branch `wip/rd-build-deb-depends`,
   worktree `.rd-work/wt/dr-desktop-apps`): `package/deb/template/control.m4` Depends gains libnss3,
   libpulse-mainloop-glib0 and the five xcb libraries. After that `apt-get install ./ration-docs_*.deb`
   pulls everything and `ldd` finds every library except the unused Wayland/EGLFS Qt platform plugins.
4. Not a blocker, but a repository defect found on the way: desktop-apps commit fc625f1ea (#1513)
   committed `common/loginpage/build/node_modules` as a **symlink to an absolute path on the Mac**
   (`desktop-apps/common/loginpage/build/node_modules` (pointing at a developer's absolute path), mode 120000), which in the
   main checkout points at itself ("Too many levels of symbolic links"). On Linux it is dangling and
   `npm install` replaces it, so the build is unaffected; on the Mac it breaks the start page build until
   the link is removed. It should be deleted from the tree and `node_modules` left to .gitignore.

## Checks on the result

- `make.py` ends with `[symbols] ok - every import of ours is satisfied inside the payload`.
- `ldd -r` on RationDocs, libascdocumentscore.so, editors_helper and converter/x2t (LD_LIBRARY_PATH=payload:payload/converter): no undefined symbols.
- Payload 1.9 GB: Qt 5.15.2 (+ICU 56, qml, plugins), CEF 109.1.18, converter/ with x2t and ICU 74,
  editors/ with sdkjs, web-apps, sdkjs-plugins including the plugin manager `{AA2EA9B6-...}`.
- Package: name `ration-docs`, version `2026.2.0-1`, Maintainer `Stackchase Limited <apps@stackchase.com>`,
  `/usr/bin/ration-docs` -> `/opt/ration/docs/RationDocs`, `/usr/share/applications/ration-docs.desktop`
  (`Name=Ration Docs`, `Icon=ration-docs`, `StartupWMClass=ration-docs`, scheme `rationdocs`), hicolor
  `ration-docs.png` 16..256. The only "onlyoffice" paths in the package are the ONLYOFFICE cloud connector
  under `providers/onlyoffice/`. About shows "Ration Docs, Version 2026.2.0.1 (x64 deb)".
- Running: x2t converts docx -> pdf (`Producer (Ration Docs/2026.2.0.1)`).

## Test container (`rd-linux-test`)

```dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
  xvfb x11-utils x11-xserver-utils xdotool xauth dbus-x11 openbox libnotify-bin notification-daemon imagemagick \
  ca-certificates curl python3 util-linux procps psmisc file gsettings-desktop-schemas libglib2.0-bin xdg-utils \
  && rm -rf /var/lib/apt/lists/*
COPY ration-docs.deb /tmp/ration-docs.deb
RUN apt-get update && apt-get install -y /tmp/ration-docs.deb && rm -rf /var/lib/apt/lists/*
```

Xvfb :99 1600x1000 + openbox with `<margins><top>40</top></margins>` (gives `_NET_WORKAREA` 0,40,1600,960,
a top panel for #661) + `dbus-launch`; the app runs as uid 1000 with
`--ascdesktop-support-debug-info --remote-debugging-port=9222` and is driven with xdotool (real X input)
and CDP (`--network host`, then an SSH `-L` forward). Traps:
- `pkill -f <path>` from `docker exec bash -c "..."` kills the exec'd shell too (its own command line
  matches); use `pkill -x RationDocs`.
- Killed apps stay as zombies (the container's PID 1 is a shell); harmless.
- A second instance under `unshare -r` (user namespace) dies in gtk_init ("Can't create a GtkStyleContext
  without a display connection", SIGTRAP) - an artefact of the user namespace, not of the network one.
  For a separate network namespace use a second container with `--network none` sharing the X socket
  directory and `$XDG_RUNTIME_DIR` through bind mounts.
- The container's locale is POSIX unless `LANG=C.UTF-8` is set; xdotool cannot type non-ASCII then
  (`LC_ALL=C.UTF-8 xdotool type ...`).
