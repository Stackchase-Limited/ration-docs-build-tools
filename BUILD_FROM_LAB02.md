# Building a Ration Docs release from lab02

How to build a tagged Ration Docs Desktop release on a machine that has never had the sources. The
example is the **Linux ARM64** package of **v2026.3.1**. For other releases, change the tag.

The machine needs read access to lab02 (`https://lab02.ration.works/ration/...`) with its own
credentials. Never copy anyone else's credentials onto a build machine.

## 1. What a release is made of

The `v2026.3.1` tag is on every repository below, and each tag is at the commit the released Mac and
Linux x64 packages were built from. Check out the tag in every repository, never a branch.

| Directory | lab02 repository | v2026.3.1 commit |
|---|---|---|
| (superproject) | ration-docs-desktop | 4b5400d |
| core | ration-docs-core | 104f3c7400 |
| sdkjs | ration-docs-sdkjs | 685d601fc2 |
| web-apps | ration-docs-web-apps | 421379f73f |
| desktop-sdk | ration-docs-desktop-sdk | 46ddc076c7 |
| desktop-apps | ration-docs-desktop-apps | 6783fc9a6 |
| dictionaries | ration-docs-dictionaries | 27dae48 (pinned by the superproject; no new tag) |
| build_tools | ration-docs-build-tools | 944a5c8 |
| core-fonts | ration-docs-core-fonts | 7030c66 |
| document-templates | ration-docs-document-templates | 71430c9 |
| onlyoffice.github.io | ration-docs-onlyoffice.github.io | 3a3a6961 |

The last four are not submodules. Clone them separately into the superproject directory.

core-fonts and document-templates ask for credentials over HTTPS, even where the other repositories
clone without them. Give the build machine read access to those two, or clone them over SSH
(`git@lab02.ration.works:ration/<repo>.git`).

## 2. Clone

`.gitmodules` points at GitHub, which lags behind lab02 and does not have these commits. Point every
submodule at lab02 **before** `git submodule update`:

```bash
L=https://lab02.ration.works/ration
TAG=v2026.3.1
git clone --branch $TAG $L/ration-docs-desktop.git ration-docs-desktop
cd ration-docs-desktop
for s in core sdkjs web-apps desktop-sdk desktop-apps dictionaries; do
  git config submodule.$s.url $L/ration-docs-$s.git
done
git submodule update --init          # checks out the commits the tag pins
for r in build-tools:build_tools core-fonts:core-fonts document-templates:document-templates \
         onlyoffice.github.io:onlyoffice.github.io; do
  git clone --branch $TAG $L/ration-docs-${r%%:*}.git ${r#*:}
done
```

Check that every repository is at its tag before building. Each line must print `ok`:

```bash
for d in . core sdkjs web-apps desktop-sdk desktop-apps build_tools core-fonts document-templates onlyoffice.github.io; do
  [ "$(git -C $d rev-parse HEAD)" = "$(git -C $d rev-parse $TAG^{commit})" ] && echo "ok $d" || echo "WRONG $d"
done
[ "$(git -C dictionaries rev-parse HEAD)" = "$(git ls-tree HEAD dictionaries | awk '{print $3}')" ] && echo "ok dictionaries"
```

`build_tools/version` must read `2026.3.1`.

## 3. Linux ARM64: host and build image

- **Host:** ARM64 (aarch64) with Docker: an Apple Silicon Mac with Docker Desktop, or ARM64 Linux.
  It needs about **100 GB free** for Docker (the tree is about 36 GB after a build, plus the image
  and caches), **8 GB memory** for the container plus swap, and 6 or more CPUs.
- **Build image:** the `rd-builder` Dockerfile in `LINUX_X64_DESKTOP_BUILD.md`, built on the ARM64
  host so that `ubuntu:24.04` is the arm64 image. Change one thing: the Qt 5.15.2 that aqtinstall
  downloads exists only for x86-64. Replace that last `RUN` line with Ubuntu's Qt 5 development
  packages:

  ```dockerfile
  RUN apt-get update && apt-get install -y --no-install-recommends \
    qtbase5-dev qtmultimedia5-dev libqt5svg5-dev libqt5x11extras5-dev qttools5-dev qtdeclarative5-dev \
    && rm -rf /var/lib/apt/lists/*
  ```

- **Known ARM64 traps:** `ARM64_DESKTOP_BUILD.md` covers the x86-only tools in v8's fetch, a bare
  `python`, ICU naming, static libstdc++ and DNS blips during the v8 fetch. All the code fixes are
  committed; the machine-side ones (swap, DNS fallbacks) are listed there.

## 4. Configure and build

Lay the tree out as `<workdir>/tree/<repo>`, with the ten directories side by side.
`build_tools/config`:

```
module="desktop"
platform="linux_arm64"
update="0"
clean="1"
qt-dir="/usr"
sysroot="0"
beta="0"
desktop-marketplace="1"
multiprocess="0"
```

`update="0"` means make.py runs no git commands. It builds exactly what is on disk.

```bash
docker run -d --name rd-build --user $(id -u):$(id -g) --memory 7g --memory-swap 11g \
  -e HOME=/rb/home-build -e MAKEFLAGS=-j4 -e PRODUCT_VERSION=2026.3.1 -e BUILD_NUMBER=1 \
  -v $PWD:/rb -w /rb/tree/build_tools rd-builder python3 make.py
docker logs -f rd-build > make.log
```

Expect 3 to 4 hours on a first run. If it is interrupted, set `clean="0"` and run it again to resume.

**Before packaging, check that Qt is in the payload.** The .deb lists no Qt packages in Depends, so
the payload has to carry Qt itself. With `qt-dir="/usr"`, build_tools may fail to copy Ubuntu's Qt
libraries (see "Why Qt 5.15.2 from qt.io" in `LINUX_X64_DESKTOP_BUILD.md`):

```bash
ls tree/build_tools/out/linux_arm64/onlyoffice/desktopeditors/ | grep -i libQt5Core
```

If nothing is listed, stop and report it. Do not publish a package that only runs where Qt happens
to be installed.

## 5. Package

```bash
docker run --rm --user $(id -u):$(id -g) -e HOME=/rb/home-build -v $PWD:/rb rd-builder \
  bash -c "cd /rb/tree/desktop-apps/package && make clean && make deb PRODUCT_VERSION=2026.3.1 BUILD_NUMBER=1"
# -> tree/desktop-apps/package/deb/ration-docs_2026.3.1-1_arm64.deb
```

The Makefile takes the architecture from `uname -m` inside the container: aarch64 gives `arm64`.

## 6. Test before handing it over

In a fresh `ubuntu:24.04` arm64 container:

1. `apt install ./ration-docs_2026.3.1-1_arm64.deb` succeeds.
2. `ldd -r` on `RationDocs`, `editors_helper`, `libascdocumentscore.so` and `x2t` finds no missing
   libraries and no undefined symbols.
3. The app starts on Xvfb, and About shows **2026.3.1.1**.
4. x2t converts docx, xlsx and pptx to PDF.
5. The crash checks that the x64 package passed (`fork-fix-tests/rd-0114-docbuilder-txt-layout-abort`
   and `fork-fix-tests/upstream-3cf5178838-svg-css-regex-stack-overflow`) also pass here.

Then record the file size and `sha256sum`, and send the .deb and the checksum back for the release
notes. The package is unsigned, like the other 2026.3.1 packages.

## Rules for build machines

- Build only from tags. Make no commits, tags or pushes from the build machine.
- Prefix container and image names with `rd-`, and keep all work in one directory.
- Don't create hard links to release files. Copy them with `cp --no-preserve=links`, so a rebuild
  can never overwrite a published file through a link.
