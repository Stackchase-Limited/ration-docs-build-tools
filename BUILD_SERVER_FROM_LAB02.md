# Building the Ration Docs online server from lab02

How to build the Ration Docs Document Server (the online editors) on a machine that has never had the
sources. The result is a .deb and a Docker image. The desktop recipe is `BUILD_FROM_LAB02.md`; this
one shares its builder image and its rules.

The machine needs read access to lab02 with its own credentials. Never copy anyone else's credentials
onto a build machine.

## 1. Pick what to build

There are two source sets. Both use the same steps, and only the refs and `BUILD_NUMBER` differ.

**A. Release 2026.3.1: the tested server.** Check out `v2026.3.1` in every repository. This rebuilds the
package that was built and tested on 2026-11-23:

| Package | Size (bytes) | sha256 |
|---|---|---|
| `ration-documentserver_2026.3.1-1_amd64.deb` | 685,747,416 | `482094ac140a7e4a8cc5a885abf6b4b36fc3cb7cd56fdd4b23b0d5e4ea436e1b` |
| `rd-docs-server_2026.3.1-1_amd64.image.tar.gz` | 1,767,371,255 | `adc94d2863a3bb61b4e3598ffc1f6d5e9c8766ed2dec4ce745f578f7bb3f5766` |

The rebuilt files will not match these checksums byte for byte, because packages carry build times.

**B. Build 2026.3.1.2: A plus the later server commits.** This build has not been tested yet, so run
section 6 in full before using it. It adds:
- Ration Docs branding on the test example, its welcome pages, the sample document's logo and the
  package description;
- a "Server baseline" row in About when the editors are served online;
- the editors show the 10.0 server's temporary conversion error (-98) as an open or save error
  instead of "Unknown error".

| Directory | lab02 repository | A: ref | B: commit |
|---|---|---|---|
| core | ration-docs-core | v2026.3.1 | 104f3c7400 (same) |
| sdkjs | ration-docs-sdkjs | v2026.3.1 | 86de17db1f (`ration/v10-backports`) |
| web-apps | ration-docs-web-apps | v2026.3.1 | 6ca84097ff (`ration/v10-backports`) |
| build_tools | ration-docs-build-tools | v2026.3.1 | v2026.3.1 (same) |
| dictionaries | ration-docs-dictionaries | 27dae48 (pinned by the desktop superproject) | same |
| core-fonts | ration-docs-core-fonts | v2026.3.1 | same |
| document-templates | ration-docs-document-templates | v2026.3.1 | 7e546ed (`ration/9.4-stability`) |
| onlyoffice.github.io | ration-docs-onlyoffice.github.io | v2026.3.1 | same |
| server | ration-docs-server | v2026.3.1 | a41d7631 (`ration/10.0`) |
| document-server-package | ration-docs-document-server-package | v2026.3.1 | 5af32d7 (`ration/10.0`) |
| document-server-integration | ration-docs-document-server-integration | v2026.3.1 | f43275a4 (`ration/10.0`) |
| document-formats | ration-docs-document-formats | v2026.3.1 | same |

For B, check out the commit hashes, not the branch names, so that later pushes cannot change what
you build. Build B with `PRODUCT_VERSION=2026.3.1 BUILD_NUMBER=2`. The version must stay 2026.3.1: the
editors compare their version with the server's, and a mismatch makes open editors keep reloading.

The server code is ONLYOFFICE Docs 10.0, and the editors are our 9.4 line with backports. That
combination was tested on 2026-11-23: co-editing, saving, conversion, and the version check passed.

## 2. Clone

desktop-apps and desktop-sdk are not needed. `.gitmodules` points at GitHub, so take `dictionaries` by
the commit the desktop superproject pins.

```bash
L=https://lab02.ration.works/ration
TAG=v2026.3.1
mkdir -p ~/rd-server/tree && cd ~/rd-server/tree
for r in core sdkjs web-apps build-tools:build_tools core-fonts document-templates \
         onlyoffice.github.io server document-server-package document-server-integration document-formats; do
  git clone --branch $TAG $L/ration-docs-${r%%:*}.git ${r#*:}
done
git clone $L/ration-docs-dictionaries.git dictionaries && git -C dictionaries checkout 27dae48
```

- core-fonts, document-templates and the three server repositories may ask for credentials over HTTPS.
  Clone those over SSH (`git@lab02.ration.works:ration/<repo>.git`) or give the machine read access.
- Do not initialise the submodules of document-server-integration. They point outside lab02, and the
  build does not need them.

**For B only**, move six repositories to their commits:

```bash
git -C sdkjs checkout 86de17db1f;  git -C web-apps checkout 6ca84097ff
git -C document-templates checkout 7e546ed
git -C server checkout a41d7631;   git -C document-server-package checkout 5af32d7
git -C document-server-integration checkout f43275a4
```

Check that the working trees are clean and at the right commits (`git -C <dir> status` and
`git -C <dir> log -1 --oneline`). `build_tools/version` must read `2026.3.1`.

## 3. Builder image

1. Build `rd-builder` from the Dockerfile in `LINUX_X64_DESKTOP_BUILD.md`.
   - On ARM64, apply the Qt change in `BUILD_FROM_LAB02.md` section 3.
2. Build `rd-server-builder` on top of it. It adds Node.js 20, which the server's `engines` requires
   and which `pkg` targets, plus `@yao-pkg/pkg`:

```dockerfile
FROM rd-builder:latest
ARG NODE_VER=20.19.5
ARG NODE_ARCH=x64
RUN cd /tmp && curl -fsSLO https://nodejs.org/dist/v${NODE_VER}/node-v${NODE_VER}-linux-${NODE_ARCH}.tar.xz \
 && curl -fsSLO https://nodejs.org/dist/v${NODE_VER}/SHASUMS256.txt \
 && grep " node-v${NODE_VER}-linux-${NODE_ARCH}.tar.xz\$" SHASUMS256.txt | sha256sum -c - \
 && tar -xJf node-v${NODE_VER}-linux-${NODE_ARCH}.tar.xz -C /usr/local --strip-components=1 \
      --exclude=CHANGELOG.md --exclude=LICENSE --exclude=README.md \
 && rm -f node-v${NODE_VER}-linux-${NODE_ARCH}.tar.xz SHASUMS256.txt \
 && /usr/local/bin/npm install -g grunt-cli@1.5.0 @yao-pkg/pkg@6.11.0 && rm -rf /root/.npm
ENV PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin
```

```bash
docker build -t rd-server-builder .                          # x86-64
docker build --build-arg NODE_ARCH=arm64 -t rd-server-builder .   # ARM64
```

## 4. Configure and build

`tree/build_tools/config`:

```
module="server"
platform="linux_64"
update="0"
clean="1"
qt-dir="/opt/qt/5.15.2"
sysroot="0"
beta="0"
multiprocess="0"
server-addons=""
web-apps-addons=""
```

- `update="0"` means make.py runs no git commands; it builds exactly what is on disk.
- Empty addons give the open-source edition. That edition does not need `server-admin-panel`.
- **ARM64:** use `platform="linux_arm64"` and `qt-dir="/usr"`. The ARM64 server build has not been
  tried; see the known traps in `ARM64_DESKTOP_BUILD.md`.

```bash
cd ~/rd-server
docker run -d --name rd-server-build --user $(id -u):$(id -g) --memory 6500m --memory-swap 6500m \
  -e HOME=/rb/home-build -e MAKEFLAGS=-j2 -e PRODUCT_VERSION=2026.3.1 -e BUILD_NUMBER=1 \
  -v $PWD:/rb -w /rb/tree/build_tools rd-server-builder python3 make.py
docker logs -f rd-server-build > make.log
```

- Use `BUILD_NUMBER=2` for B.
- The tested run took 42 minutes at `-j2`, but it reused third-party libraries (v8, boost, ICU,
  OpenSSL) built earlier. On a fresh machine, expect 3 to 4 hours.
- Memory peaked at 5.9 GB. Raise `-j` only if the machine has more memory.
- If the build is interrupted, set `clean="0"` and run it again to resume.

Check the version in the build output before packaging:

```bash
grep -o "2026\.3\.1'" tree/build_tools/out/linux_64/onlyoffice/documentserver/web-apps/apps/api/documents/api.js | head -1
```

It must print `2026.3.1'`.

## 5. Package

```bash
docker run --rm --user $(id -u):$(id -g) -e HOME=/rb/home-build -v $PWD:/rb \
  -w /rb/tree/document-server-package rd-server-builder \
  bash -c "make clean && make deb PRODUCT_VERSION=2026.3.1 BUILD_NUMBER=1"
# -> tree/document-server-package/deb/ration-documentserver_2026.3.1-1_amd64.deb   (B: ..._2026.3.1-2_...)
```

- The package lists no PostgreSQL, RabbitMQ or Redis in Depends, because the open-source 10.0 server
  does not use them (see section 7).
- To build the Docker image, put the .deb next to the package's own Docker recipe:

```bash
mkdir -p image && cp tree/document-server-package/docker/{Dockerfile,entrypoint.sh,supervisord.conf} image/
cp --no-preserve=links tree/document-server-package/deb/ration-documentserver_*.deb image/
docker build --build-arg PACKAGE_VERSION=2026.3.1-1 \
  --build-arg SOURCE_URL=https://lab02.ration.works/ration/ration-docs-server \
  --build-arg SOURCE_REVISION=$(git -C tree/server rev-parse HEAD) \
  --build-arg PACKAGING_REVISION=$(git -C tree/document-server-package rev-parse HEAD) \
  -t rd-docs-server:2026.3.1 image
docker save rd-docs-server:2026.3.1 | gzip -1 > rd-docs-server_2026.3.1-1_amd64.image.tar.gz
```

## 6. Test before handing it over

Run everything bound to 127.0.0.1, and reach it over an SSH tunnel. Use throwaway secrets made on
the machine, never production ones.

```bash
umask 077; JWT=$(openssl rand -hex 32); SL=$(openssl rand -hex 24)
docker network create rd-docs-net
docker run -d --name rd-docs-server --network rd-docs-net -p 127.0.0.1:18090:80 --memory 3g \
  -e JWT_SECRET=$JWT -e SECURE_LINK_SECRET=$SL rd-docs-server:2026.3.1
```

The test example is a separate, test-only container. It is the example app from the build plus
`socat`, so the example reaches the server at the same URL the browser uses:

```dockerfile
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends socat ca-certificates && rm -rf /var/lib/apt/lists/*
COPY documentserver-example /opt/example
RUN mkdir -p /data/files && chown -R 1000:1000 /data
USER 1000:1000
WORKDIR /opt/example
EXPOSE 3000
CMD ["bash","-c","socat TCP-LISTEN:18090,fork,reuseaddr,bind=127.0.0.1 TCP:rd-docs-server:80 & exec ./example"]
```

Build it with `documentserver-example` copied from `tree/build_tools/out/linux_64/onlyoffice/`, and
tag it `rd-docs-example:2026.3.1`. Then run it:

```bash
docker run -d --name rd-docs-example --network rd-docs-net -p 127.0.0.1:13000:3000 --memory 512m \
  -e NODE_CONFIG="{\"server\":{\"siteUrl\":\"http://localhost:18090/\",\"exampleUrl\":\"http://rd-docs-example:3000\",\"storageFolder\":\"/data/files\",\"token\":{\"enable\":true,\"secret\":\"$JWT\"}}}" \
  rd-docs-example:2026.3.1
```

`exampleUrl` must not end in a slash, or downloads fail. From your own machine, open the tunnel with
`ssh -N -L 18090:127.0.0.1:18090 -L 13000:127.0.0.1:13000 <build machine>`, then go to
http://localhost:13000/.

Every test must pass:

1. **Co-editing:** open one document in two separate browser profiles. Each side's typing appears on
   the other within seconds, both show 2 users, and both show "All changes saved".
2. **Saving:** close both editors. The saved file contains both edits and reopens without a version
   alert.
3. **Version:** About shows **2026.3.1.1** (B: **2026.3.1.2**). The server log says
   `Version: 2026.3.1. Build: 1` (B: `Build: 2`). No "editor updated" message appears.
4. **Other editors:** an xlsx and a pptx open without errors.
5. **Conversion:** docx to PDF through `/converter/from-file` returns HTTP 200. The SVG inputs from
   `fork-fix-tests/upstream-3cf5178838-svg-css-regex-stack-overflow` convert without crashing the
   server.
6. **B only:**
   - the example pages and the sample document show Ration Docs;
   - About has a "Server baseline" row;
   - `apt-cache show ./ration-documentserver_*.deb` (or `dpkg -I`) shows the Ration Docs description.

Record the sizes and `sha256sum` of the .deb and the image tarball, and send them back with the test
results. Then stop and remove the test containers. The packages are unsigned.

## 7. Before deploying

- **Single instance per document.** The open-source 10.0 server keeps co-editing sessions, its task
  queue and its pub/sub in memory, in one process. Every user editing the same document must reach
  the same server process.
  - Separate servers that each serve their own users are fine.
  - Behind a load balancer, route by document key, or editors on different servers will not see each
    other's changes, and saves can overwrite each other.
  - A restart ends the open sessions.
- **Access tokens.** 10.0 checks JWTs more strictly: per-purpose checks, the `operation` claim on
  `/converter/from-file`, and the public default secret is refused. Test every integration that
  calls the server before switching it over.
- **Corresponding source (AGPL section 13).** About links to `https://ration.works/source`. That page
  must lead to the exact source of the running server, including the server and
  document-server-package repositories at the deployed commits.
- **Production setup:** real secrets, TLS and a reverse proxy are needed, and the test example must
  not be deployed.

## Rules for build machines

- Build only from tags or exact commits. Make no commits, tags or pushes from the build machine.
- Prefix container and image names with `rd-`, and keep all work in one directory.
- Don't create hard links to release files. Copy them with `cp --no-preserve=links`.
