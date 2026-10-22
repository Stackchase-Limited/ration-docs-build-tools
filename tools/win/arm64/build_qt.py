"""Build Qt 5.15.2 for win_arm64 on a Windows ARM64 machine, into qt_build/Qt-5.15.2/win_arm64.

This is the Qt the win_arm64 desktop build uses (scripts/base.py qt_dir override). It
replaces the prebuilt qt_binary_win_arm64.7z that fetch_qt.py used to download from
ONLYOFFICE-data: that package crashes in every Qt program - QObjectPrivate::addConnection,
the first time anything connects a signal - because of the miscompile patched below. Its
Qt5Core was rebuilt separately from the other modules and still carries the same bug.

What this does, and why each differs from a stock Qt build:

- Source: the official qt-everywhere-src-5.15.2 tarball from download.qt.io, checked
  against its published SHA-256.
- Native build: -platform win32-arm64-msvc2017 under `vcvarsall x64_arm64`. VS 2019 has
  only x64-hosted compilers, which Windows on ARM runs under emulation; the tools Qt
  builds (qmake, moc, uic, rcc) are ARM64 and run natively. -xplatform does not work
  here: Qt 5.15 cannot recognise an ARM64 host (see the toolchain.prf patch).
- Patch toolchain.prf: qmake 5.15 reports an ARM64 Windows host as "Unknown", so the
  mkspec's msvc_cross step called `vcvarsall Unknown_arm64` and configure stopped. The
  host is mapped to amd64, which is what the compilers are.
- Patch qobject_p.h: MSVC 14.29 for ARM64 drops the value-initialisation of the
  ConnectionList() temporary in QObjectPrivate::ConnectionData::resizeSignalVector and
  copies stack garbage into every new signal slot. The first connect() then writes
  through a wild pointer (uic --version, a hello-world QLabel and Ration Docs all
  crashed there). Both pointers are cleared explicitly instead.
- jom (download.qt.io) for a parallel build; nmake builds one file at a time.
- The source is unpacked to a short path (RATION_QT_SRC, default C:\\qt5src) to keep
  Qt's deep tree clear of path-length limits.
- Python is put on PATH through a space-free junction. configure records the Python it
  finds (QMAKE_PYTHON) and qtdeclarative's Makefiles run it unquoted, so a Python under
  "C:\\Program Files" fails with "'C:\\Program' is not recognized" at RegExpJitTables.h.

It takes hours. The result is reused: build_tools only needs qt_build/ to exist.
"""

import hashlib
import os
import sys
import urllib.request
import zipfile

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/../../../scripts')

import base

QT_VERSION = "5.15.2"
QT_URL = "https://download.qt.io/archive/qt/5.15/5.15.2/single/qt-everywhere-src-5.15.2.tar.xz"
QT_SHA256 = "3a530d1b243b5dec00bc54937455471aaa3e56849d2593edb8ded07228202240"
JOM_URL = "https://download.qt.io/official_releases/jom/jom.zip"

HERE = os.path.dirname(os.path.abspath(__file__))
PREFIX = HERE + "/qt_build/Qt-5.15.2/win_arm64"
SRC_ROOT = os.environ.get("RATION_QT_SRC", "C:/qt5src")
SRC = SRC_ROOT + "/qt-everywhere-src-5.15.2"

MARK = "ration-docs win_arm64"


def get_vs_path(version="2019"):
  program_files = base.get_env("ProgramFiles(x86)") or base.get_env("ProgramFiles")
  for edition in ("Enterprise", "Professional", "Community"):
    path = program_files + "/Microsoft Visual Studio/" + version + "/" + edition + "/VC/Auxiliary/Build"
    if base.is_dir(path):
      return path
  return program_files + "/Microsoft Visual Studio/" + version + "/Community/VC/Auxiliary/Build"


def sha256(path):
  h = hashlib.sha256()
  with open(path, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
      h.update(chunk)
  return h.hexdigest()


def fetch_source():
  tarball = HERE + "/qt_source_5.15.2.tar.xz"
  if not base.is_file(tarball) or sha256(tarball) != QT_SHA256:
    print("[qt] downloading " + QT_URL)
    urllib.request.urlretrieve(QT_URL, tarball)
  if sha256(tarball) != QT_SHA256:
    raise SystemExit("[qt] checksum mismatch for " + tarball)
  if not base.is_file(SRC + "/configure.bat"):
    base.create_dir(SRC_ROOT)
    base.cmd("tar", ["-xf", tarball, "-C", SRC_ROOT])


def patch(path, old, new):
  """Replace `old` with `new` once; a no-op when the patch is already in."""
  with open(path, "rb") as f:
    data = f.read().decode("utf-8")
  if MARK in data:
    return
  nl = "\r\n" if "\r\n" in data else "\n"
  old, new = old.replace("\n", nl), new.replace("\n", nl)
  if data.count(old) != 1:
    raise SystemExit("[qt] patch anchor not found in " + path)
  with open(path, "wb") as f:
    f.write(data.replace(old, new).encode("utf-8"))
  print("[qt] patched " + path)


def apply_patches():
  patch(SRC + "/qtbase/mkspecs/features/toolchain.prf",
        "        equals(hostArch, x86_64): \\\n"
        "            hostArch = amd64\n",
        "        equals(hostArch, x86_64): \\\n"
        "            hostArch = amd64\n"
        "        # " + MARK + ": qmake 5.15 reports an ARM64 Windows host as \"Unknown\"; VS 2019\n"
        "        # only has x64-hosted compilers there, which run under emulation.\n"
        "        equals(hostArch, Unknown): \\\n"
        "            hostArch = amd64\n")
  patch(SRC + "/qtbase/src/corelib/kernel/qobject_p.h",
        "                newVector->at(i) = ConnectionList();\n",
        "            {\n"
        "                // " + MARK + ": MSVC 14.29 for ARM64 drops the value-initialisation\n"
        "                // of the ConnectionList() temporary and copies stack garbage into every\n"
        "                // slot, so the first connect() writes through a wild pointer.\n"
        "                newVector->at(i).first.storeRelaxed(nullptr);\n"
        "                newVector->at(i).last.storeRelaxed(nullptr);\n"
        "            }\n")


def python_dir():
  """Directory of this Python, reached through a junction if its path has spaces."""
  real = os.path.dirname(sys.executable)
  if " " not in real:
    return real
  link = SRC_ROOT + "/python"
  if not os.path.isdir(link):
    base.create_dir(SRC_ROOT)
    base.cmd("cmd", ["/c", "mklink", "/J", link.replace("/", "\\"), real])
  return link


def jom_path():
  jom_dir = SRC_ROOT + "/jom"
  if not base.is_file(jom_dir + "/jom.exe"):
    base.create_dir(jom_dir)
    archive = jom_dir + "/jom.zip"
    urllib.request.urlretrieve(JOM_URL, archive)
    with zipfile.ZipFile(archive) as z:
      z.extractall(jom_dir)
  return jom_dir


def make():
  if not base.is_os_arm():
    raise SystemExit("[qt] build_qt.py builds a native win_arm64 Qt; run it on Windows on ARM.")
  fetch_source()
  apply_patches()

  params = ["-opensource", "-confirm-license", "-release", "-shared", "-accessibility",
            "-prefix", "\"" + PREFIX + "\"",
            "-extprefix", "\"" + PREFIX + "\"",
            "-hostprefix", "\"" + PREFIX + "\"",
            "-c++std", "c++11",
            "-qt-zlib", "-qt-libpng", "-qt-libjpeg", "-qt-pcre",
            "-no-sql-sqlite", "-no-qml-debug",
            "-nomake", "examples", "-nomake", "tests",
            "-skip", "qtlocation", "-skip", "qtserialport", "-skip", "qtsensors",
            "-skip", "qtxmlpatterns", "-skip", "qt3d", "-skip", "qtwebview",
            "-skip", "qtwebengine",
            "-platform", "win32-arm64-msvc2017",
            "-no-pch"]

  bat = []
  bat.append("call \"" + get_vs_path() + "/vcvarsall.bat\" x64_arm64")
  bat.append("set PATH=" + python_dir().replace("/", "\\") + ";" + jom_path().replace("/", "\\") + ";%PATH%")
  bat.append("cd /d \"" + SRC.replace("/", "\\") + "\"")
  bat.append("if not exist Makefile call configure.bat " + " ".join(params))
  bat.append("jom -j %NUMBER_OF_PROCESSORS%")
  bat.append("jom install")
  base.run_as_bat(bat)

  if not base.is_file(PREFIX + "/bin/Qt5Core.dll"):
    raise SystemExit("[qt] build finished without " + PREFIX + "/bin/Qt5Core.dll")


if __name__ == "__main__":
  make()
