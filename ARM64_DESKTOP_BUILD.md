# Native ARM64 Desktop Build

Ration Docs Desktop can be built natively for Ubuntu ARM64. The build tooling
supports the `linux_arm64` target and supplies ARM64 Qt and sysroot inputs.

## Requirements

- Ubuntu 24.04 ARM64 with Docker
- At least 8 GB RAM and 4 GB swap
- At least 100 GB of free storage available to Docker

## Stock 9.4 verification build

From the root of this repository, run:

```bash
./tools/linux/build-desktop-arm64-docker.sh
```

The wrapper builds a native `linux/arm64` Ubuntu image and invokes:

```bash
python3 ./automate.py desktop --branch=release/v9.4.0
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
