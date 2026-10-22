"""Provide the win_arm64 Qt in qt_build/Qt-5.15.2/win_arm64.

This used to download qt_binary_win_arm64.7z from ONLYOFFICE-data. That prebuilt Qt
crashes in every Qt program (QObjectPrivate::addConnection; see build_qt.py), so it is
no longer used: Qt is built from the official source by build_qt.py instead.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import build_qt


def make():
  if os.path.isfile(build_qt.PREFIX + "/bin/Qt5Core.dll"):
    return
  build_qt.make()


if __name__ == "__main__":
  make()
