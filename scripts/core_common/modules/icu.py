#!/usr/bin/env python

import sys
sys.path.append('../..')
sys.path.append('android')
import config
import base
import os
import glob
import icu_android

def fetch_icu(major, minor, target_dir="icu"):
  if (base.is_dir("./icu2")):
    base.delete_dir_with_access_error("icu2")
  base.cmd("git", ["clone", "--depth", "1", "--branch", "release-" + major + "-" + minor, "https://github.com/unicode-org/icu.git", "./icu2"])
  base.copy_dir("./icu2/icu4c", target_dir)
  base.delete_dir_with_access_error("icu2")
  return

def clear_module():
  if base.is_dir("icu"):
    base.delete_dir_with_access_error("icu")

  # remove build
  for child in glob.glob("./*"):
    if base.is_dir(child):
      base.delete_dir(child)

  return

def make():
  print("[fetch & build]: icu")

  base_dir = base.get_script_dir() + "/../../core/Common/3dParty/icu"
  old_cur = os.getcwd()
  os.chdir(base_dir)

  base.check_module_version("8", clear_module)

  if (-1 != config.option("platform").find("android")):
    icu_android.make()

  os.chdir(base_dir)

  icu_major = "74"
  icu_minor = "2"

  if not base.is_dir("icu"):
    fetch_icu(icu_major, icu_minor)

  # old version for win_xp
  icu_major_old = "58"
  icu_minor_old = "3"

  if config.check_option("platform", "win_64_xp") or config.check_option("platform", "win_32_xp"):
    if not base.is_dir("icu58"):
      fetch_icu(icu_major_old, icu_minor_old, "icu58")

  if ("windows" == base.host_platform()):
    platformToolset = "v140"
    if (config.option("vs-version") == "2019"):
      platformToolset = "v142"
    need_platforms = []
    if (-1 != config.option("platform").find("win_64")):
      need_platforms.append("win_64")
    if (-1 != config.option("platform").find("win_32")):
      need_platforms.append("win_32")
    if (-1 != config.option("platform").find("win_arm64")):
      need_platforms.append("win_64") # for exe files
      need_platforms.append("win_arm64")

    def build_icu_win(source_dir, out_dir, icu_major):
      if base.is_dir(out_dir):
        return

      compile_bat = []
      compile_bat.append("setlocal")

      args = {
        "win_32" : {
          "msbuild_platfrom" : "Win32",
          "vcvarsall_arch" : "x86",
          "out_bin_dir" : source_dir + "/bin/",
          "out_lib_dir" : source_dir + "/lib/"
        },
        "win_64" : {
          "msbuild_platfrom" : "X64",
          "vcvarsall_arch" : "x64",
          "out_bin_dir" : source_dir + "/bin64/",
          "out_lib_dir" : source_dir + "/lib64/"
        },
        "win_arm64" : {
          "msbuild_platfrom" : "ARM64",
          "vcvarsall_arch" : "x64_arm64",
          "out_bin_dir" : source_dir + "/binARM64/",
          "out_lib_dir" : source_dir + "/libARM64/"
        }
      }

      platform_args = args[platform]

      compile_bat.append("call \"" + config.option("vs-path") + "/vcvarsall.bat\" " + platform_args['vcvarsall_arch'])
      compile_bat.append("call MSBuild.exe " + source_dir + "/source/allinone/allinone.sln /p:Configuration=Release /p:PlatformToolset=" + platformToolset + " /p:Platform=" + platform_args['msbuild_platfrom'])
      compile_bat.append("endlocal")
      base.run_as_bat(compile_bat)

      base.create_dir(out_dir)
      base.copy_file(platform_args['out_bin_dir'] + "icudt" + icu_major + ".dll", out_dir)
      base.copy_file(platform_args['out_bin_dir'] + "icuuc" + icu_major + ".dll", out_dir)
      base.copy_file(platform_args['out_lib_dir'] + "icudt.lib", out_dir)
      base.copy_file(platform_args['out_lib_dir'] + "icuuc.lib", out_dir)

    for platform in need_platforms:
      if not config.check_option("platform", platform) and not config.check_option("platform", platform + "_xp"):
        continue

      if not (config.check_option("platform", "win_64_xp") or config.check_option("platform", "win_32_xp")):
        build_icu_win("icu", platform + "/build", icu_major)
      else:
        # xp
        build_icu_win("icu58", platform + "/build/xp", icu_major_old)

    os.chdir(old_cur)
    return

  if ("linux" == base.host_platform()):
    if not base.is_dir(base_dir + "/linux_64"):
      base.create_dir(base_dir + "/icu/cross_build")
      os.chdir("icu/cross_build")
      command_configure = "./../source/runConfigureICU"
      command_compile_addon = "-static-libstdc++ -static-libgcc"
      if "1" == config.option("use-clang"):
        command_configure = "CXXFLAGS=-stdlib=libc++ " + command_configure
        command_compile_addon = "-stdlib=libc++"
      if "" == config.option("sysroot"):
        # Both edits below rewrite configure's INPUT templates, so they have to
        # run BEFORE runConfigureICU, not after it. configure generates
        # cross_build/data/pkgdataMakefile and the icudefs from these templates;
        # a patch applied afterwards lands in the template only and never reaches
        # the generated copy that make actually reads. The symptom was a clean
        # checkout failing its first build on the dangling -Wl, described below
        # and then succeeding on the second, once configure re-ran over an
        # already-patched template.
        # Idempotent: this whole block is guarded by "linux_64 does not exist yet",
        # so every failed-and-retried build ran it again and appended another copy
        # of the flags - after three attempts the link line carried
        # "-static-libstdc++ -static-libgcc" three times over.
        if not base.is_file("./../source/icudefs.mk.in.rd-bak"):
            base.copy_file("./../source/icudefs.mk.in", "./../source/icudefs.mk.in.rd-bak")
        else:
            base.copy_file("./../source/icudefs.mk.in.rd-bak", "./../source/icudefs.mk.in")
        base.replaceInFile("./../source/icudefs.mk.in", "LDFLAGS = @LDFLAGS@ $(RPATHLDFLAGS)", "LDFLAGS = @LDFLAGS@ $(RPATHLDFLAGS) " + command_compile_addon)
        # Stop pkgdata emitting a dangling -Wl, when it links the data library.
        #
        # config/mh-linux defines
        #     LD_SONAME = -Wl,-soname -Wl,$(notdir $(MIDDLE_SO_TARGET))
        # and data/pkgdataMakefile.in deliberately sets MIDDLE_SO_TARGET to empty
        # before echoing LD_SONAME into icupkg.inc, so the generated value is the
        # bare "-Wl,-soname -Wl,". pkgdata then appends the library name after it,
        # producing
        #     -Wl,-soname -Wl, libicudata.so.74
        # and ld reads that trailing name as an input FILE:
        #     /usr/bin/ld: cannot find libicudata.so.74: No such file or directory
        # which surfaces only as pkgdata's "Error generating assembly code for
        # data" and looks like a data-generation problem rather than a link flag.
        #
        # pkgdata handles an empty LD_SONAME explicitly - it then omits the name
        # as well - so blanking it is the supported way out. The resulting
        # libicudata carries no SONAME, which is harmless here: pkgdata still
        # creates the libicudata.so.74 and libicudata.so symlinks, and nothing
        # loads it by SONAME.
        base.replaceInFile("./../source/data/pkgdataMakefile.in", "@echo LD_SONAME=$(LD_SONAME) >> $(OUTPUTFILE)", "@echo LD_SONAME= >> $(OUTPUTFILE)")

        base.cmd(command_configure, ["Linux", "--prefix=" + base_dir + "/icu/cross_build_install"])
      else:
        base.set_sysroot_env("linux_64") 
        sysroot_path = config.option("sysroot_linux_64")
        sysroot_path_bin = config.get_custom_sysroot_bin("linux_64")
        base.cmd_exe("./../source/configure", ["--prefix=" + base_dir + "/icu/cross_build_install",
                                           "CC=" + sysroot_path_bin + "/gcc", "CXX=" + sysroot_path_bin + "/g++",
                                           "AR=" + sysroot_path_bin + "/ar", "RANLIB=" + sysroot_path_bin + "/ranlib",
                                           "CFLAGS=--sysroot=" + sysroot_path,
                                           "CXXFLAGS=--sysroot=" + sysroot_path + " " + command_compile_addon,
                                           "LDFLAGS=--sysroot=" + sysroot_path])

      if "" == config.option("sysroot"):
        base.cmd("make", ["-j4"])
        base.cmd("make", ["install"], True)
      else:
        base.cmd_exe("make", ["-j4"])
        base.cmd_exe("make", ["install"], True)
        base.restore_sysroot_env()

      base.create_dir(base_dir + "/linux_64")
      base.create_dir(base_dir + "/linux_64/build")
      base.copy_file(base_dir + "/icu/cross_build_install/lib/libicudata.so." + icu_major + "." + icu_minor, base_dir + "/linux_64/build/libicudata.so." + icu_major)
      base.copy_file(base_dir + "/icu/cross_build_install/lib/libicuuc.so." + icu_major + "." + icu_minor, base_dir + "/linux_64/build/libicuuc.so." + icu_major)
      base.copy_dir(base_dir + "/icu/cross_build_install/include", base_dir + "/linux_64/build/include")

    # On an aarch64 host the "cross_build" above is not a cross build at all - it
    # is the native one - but it is published as linux_64 because that name is
    # hardcoded. The cross-compile branch below is then skipped (correctly: there
    # is nothing to cross-compile), so nothing ever creates linux_arm64/build and
    # the first library that links against ICU fails with a path, not a reason:
    #   /usr/bin/ld: cannot find .../icu/linux_arm64/build/libicuuc.so.74:
    #   No such file or directory
    # even though the file it wants exists, correctly built for this machine, one
    # directory over. file(1) on linux_64/build/libicuuc.so.74 says "ARM aarch64".
    if base.is_os_arm() and config.check_option("platform", "linux_arm64") and not base.is_dir(base_dir + "/linux_arm64/build"):
      base.create_dir(base_dir + "/linux_arm64")
      base.create_dir(base_dir + "/linux_arm64/build")
      base.copy_file(base_dir + "/icu/cross_build_install/lib/libicudata.so." + icu_major + "." + icu_minor, base_dir + "/linux_arm64/build/libicudata.so." + icu_major)
      base.copy_file(base_dir + "/icu/cross_build_install/lib/libicuuc.so." + icu_major + "." + icu_minor, base_dir + "/linux_arm64/build/libicuuc.so." + icu_major)
      base.copy_dir(base_dir + "/icu/cross_build_install/include", base_dir + "/linux_arm64/build/include")

    if config.check_option("platform", "linux_arm64") and not base.is_dir(base_dir + "/linux_arm64") and not base.is_os_arm():
      base.create_dir(base_dir + "/icu/linux_arm64")
      os.chdir(base_dir + "/icu/linux_arm64")
      compiler_gcc_prefix = base.get_compiler_gcc_prefix("linux_arm64")
      if config.option("sysroot") != "":
        base.set_sysroot_env("linux_arm64")
      base.cmd("./../source/configure", ["--host=arm-linux", "--prefix=" + base_dir + "/icu/linux_arm64_install", "--with-cross-build=" + base_dir + "/icu/cross_build",
        "CC=" + compiler_gcc_prefix + "gcc", "CXX=" + compiler_gcc_prefix + "g++", "AR=" + compiler_gcc_prefix + "ar", "RANLIB=" + compiler_gcc_prefix + "ranlib"])
      base.cmd("make", ["-j4"])
      base.cmd("make", ["install"], True)
      base.create_dir(base_dir + "/linux_arm64")
      base.create_dir(base_dir + "/linux_arm64/build")
      base.copy_file(base_dir + "/icu/linux_arm64_install/lib/libicudata.so." + icu_major + "." + icu_minor, base_dir + "/linux_arm64/build/libicudata.so." + icu_major)
      base.copy_file(base_dir + "/icu/linux_arm64_install/lib/libicuuc.so." + icu_major + "." + icu_minor, base_dir + "/linux_arm64/build/libicuuc.so." + icu_major)
      base.copy_dir(base_dir + "/icu/linux_arm64_install/include", base_dir + "/linux_arm64/build/include")
      if config.option("sysroot") != "":
        base.restore_sysroot_env()

      os.chdir("../..")

  if ("mac" == base.host_platform()):
    if not base.is_file("./icu/source/tools/pkgdata/pkgdata.cpp.bak"):
      base.copy_file("./icu/source/tools/pkgdata/pkgdata.cpp", "./icu/source/tools/pkgdata/pkgdata.cpp.bak")
      base.replaceInFile("./icu/source/tools/pkgdata/pkgdata.cpp", "cmd, \"%s %s -o %s%s %s %s%s %s %s\",", "cmd, \"%s %s -o %s%s %s %s %s %s %s\",")

    # mac
    if (-1 != config.option("platform").find("mac_")) and not base.is_dir("mac_64/build"):
      base.cmd_in_dir(os.path.dirname(os.path.abspath(__file__)), base.python_exe(), ["icu_mac.py"])

    # ios
    if (-1 != config.option("platform").find("ios")):
      if not base.is_dir("build"):
        base.bash("./icu_ios")

  os.chdir(old_cur)
  return
