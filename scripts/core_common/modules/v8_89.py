#!/usr/bin/env python

import sys
sys.path.append('../..')
import config
import base
import os
import re
import subprocess

def clean():
  if base.is_dir("depot_tools"):
    base.delete_dir_with_access_error("depot_tools")
    base.delete_dir("depot_tools")
  if base.is_dir("v8"):
    base.delete_dir_with_access_error("v8")
    base.delete_dir("v8")
  if base.is_exist("./.gclient"):
    base.delete_file("./.gclient")
  if base.is_exist("./.gclient_entries"):
    base.delete_file("./.gclient_entries")
  if base.is_exist("./.gclient_previous_sync_commits"):
    base.delete_file("./.gclient_previous_sync_commits")
  if base.is_exist("./.gcs_entries"):
    base.delete_file("./.gcs_entries")
  if base.is_exist("./.cipd"):
    base.delete_dir("./.cipd")
  return

def change_bootstrap():
  base.move_file("./depot_tools/bootstrap/manifest.txt", "./depot_tools/bootstrap/manifest.txt.bak")
  content = "# changed by build_tools\n\n"
  # linux-arm64 belongs here. Without it depot_tools' CIPD bootstrap refuses to
  # run on an ARM64 Linux host with
  #   Platform linux-arm64 is not supported by the CIPD client bootstrap:
  #   there's no pinned SHA256 hash for it in the *.digests file
  # and everything downstream fails as "client not configured; see gclient config",
  # which points at gclient rather than at this list. CIPD itself publishes a
  # linux-arm64 client; this manifest simply never listed it.
  content += "$VerifiedPlatform windows-amd64 windows-arm64 linux-amd64 linux-arm64 mac-amd64 mac-arm64\n\n"

  content += "@Subdir python\n"
  content += "infra/3pp/tools/cpython/${platform} version:2@2.7.18.chromium.39\n\n"

  content += "@Subdir python3\n"

  # One pin for every host. depot_tools' own fetch.py uses
  # argparse.BooleanOptionalAction, which is Python 3.9+, so the 3.8.10 that used
  # to be pinned everywhere except Windows made a fresh clone unusable:
  #   File "./depot_tools/fetch.py", line 247, in handle_args
  #       action=argparse.BooleanOptionalAction,
  #   AttributeError: module 'argparse' has no attribute 'BooleanOptionalAction'
  # fetch is invoked with errors suppressed, so that surfaced only much later as a
  # missing v8 directory. Windows was already on 3.11.8 and unaffected; this is
  # not architecture-specific, it is a stale pin against current depot_tools.
  content += "infra/3pp/tools/cpython3/${platform} version:2@3.11.8.chromium.35\n\n"

  content += "@Subdir git\n"
  content += "infra/3pp/tools/git/${platform} version:2@2.41.0.chromium.11\n"

  base.replaceInFile("./depot_tools/bootstrap/bootstrap.py", 
    "raise subprocess.CalledProcessError(proc.returncode, argv, None)", "return")

  base.replaceInFile("./depot_tools/bootstrap/bootstrap.py", 
    "    _win_git_bootstrap_config()", "    #_win_git_bootstrap_config()")
  
  base.writeFile("./depot_tools/bootstrap/manifest.txt", content)
  return

def is_ubuntu_24_or_higher():
  try:
    with open('/etc/os-release') as f:
      for line in f:
        if line.startswith('VERSION_ID='):
          version = line.split('=')[1].strip().strip('"')
          return float(version) >= 24
  except:
      pass
  return False

def fix_ubuntu24():
  #if not is_ubuntu_24_or_higher():
  #  return

  if "" == config.option("sysroot"):
    return

  old_cur = os.getcwd()
  os.chdir("third_party/llvm-build/Release+Asserts/lib")
  base.cmd("mv", ["libstdc++.so.6", "libstdc++.so.6.old"])
  # The multiarch directory is per-architecture; hardcoding the x86_64 one makes
  # this a dangling symlink on any other host.
  host_multiarch = "aarch64-linux-gnu" if base.is_os_arm() else "x86_64-linux-gnu"
  base.cmd("ln", ["-s", "/usr/lib/" + host_multiarch + "/libstdc++.so.6", "libstdc++.so.6"])
  os.chdir(old_cur)
  return

def system_clang_prefix():
  """Point gn at the host's own clang instead of v8's bundled x86-64 one.

  v8 ships a clang under third_party/llvm-build, and that binary is x86-64 only:
  on aarch64 ninja dies at step 1 with
    /bin/sh: 1: ../../third_party/llvm-build/Release+Asserts/bin/clang++: Exec format error
  and file(1) on it says "ELF 64-bit LSB ... x86-64". This is the third failure
  of the same family - v8's DEPS assumes an x86 host - after the x86-64 python
  bundle check_python() used to force onto ARM and the x86-64 rustc that
  enable_rust=false works around.

  The host clang works, but gn needs a clang_rt.builtins archive at the exact
  path build/config/clang/BUILD.gn computes, which is the per-target layout
    $clang_base_path/lib/clang/$clang_version/lib/aarch64-unknown-linux-gnu/libclang_rt.builtins.a
  while Debian/Ubuntu's llvm packages use the older flat layout
    .../lib/clang/18/lib/linux/libclang_rt.builtins-aarch64.a
  so ninja refuses before compiling anything:
    ninja: error: '...../aarch64-unknown-linux-gnu/libclang_rt.builtins.a',
    needed by 'obj/libv8_libbase.a', missing and no known rule to make it

  Rather than writing into /usr - which needs root and is machine state nobody
  can see from the tree - this builds a small prefix of symlinks inside the
  checkout and hands gn that. Returns (base_path, major_version), or None when
  there is no usable system clang, in which case the caller leaves the bundled
  toolchain alone.

  Run from the v8 checkout root (make_args' caller chdir's there).
  """
  version_info = base.run_command("clang --version")
  if 0 != version_info["returncode"]:
    return None
  version_match = re.search(r"clang version (\d+)", version_info["stdout"])
  if not version_match:
    return None
  version = version_match.group(1)

  resource_info = base.run_command("clang -print-resource-dir")
  if 0 != resource_info["returncode"]:
    return None
  resource_dir = resource_info["stdout"]

  # gn's directory name for linux/arm64; this helper is only called for that.
  triple_dir = "aarch64-unknown-linux-gnu"

  # A clang built with LLVM_ENABLE_PER_TARGET_RUNTIME_DIR already matches gn's
  # expectation, so /usr can be used directly with no shim.
  if base.is_file(os.path.join(resource_dir, "lib", triple_dir, "libclang_rt.builtins.a")):
    return ("/usr", version)

  flat_builtins = os.path.join(resource_dir, "lib", "linux", "libclang_rt.builtins-aarch64.a")
  if not base.is_file(flat_builtins):
    # No builtins archive at all - clang is installed without compiler-rt.
    return None

  clang_bin = base.run_command("readlink -f $(command -v clang)")["stdout"]
  if "" == clang_bin:
    return None

  prefix = os.path.abspath("third_party/rd-system-clang")
  lib_dir = os.path.join(prefix, "lib", "clang", version, "lib", triple_dir)
  base.create_dir(lib_dir)

  bin_link = os.path.join(prefix, "bin")
  if not os.path.exists(bin_link):
    # clang finds its own resource dir from the real binary path, so a symlinked
    # bin/ is enough - headers still resolve to the packaged ones.
    base.cmd("ln", ["-s", os.path.dirname(clang_bin), bin_link])

  builtins_link = os.path.join(lib_dir, "libclang_rt.builtins.a")
  if not os.path.exists(builtins_link):
    base.cmd("ln", ["-s", flat_builtins, builtins_link])

  # Older build/ checkouts (v8 8.9's own is from 2021) look for the flat name
  # under lib/linux instead, so mirror it there too rather than betting on which
  # vintage of build/config/clang/BUILD.gn the tree ends up with.
  flat_dir = os.path.join(prefix, "lib", "clang", version, "lib", "linux")
  base.create_dir(flat_dir)
  flat_link = os.path.join(flat_dir, "libclang_rt.builtins-aarch64.a")
  if not os.path.exists(flat_link):
    base.cmd("ln", ["-s", flat_builtins, flat_link])

  return (prefix, version)

def make_args(args, platform, is_64=True, is_debug=False):
  args_copy = args[:]
  if is_64:
    args_copy.append("target_cpu=\\\"x64\\\"") 
    args_copy.append("v8_target_cpu=\\\"x64\\\"")
  else:
    args_copy.append("target_cpu=\\\"x86\\\"") 
    args_copy.append("v8_target_cpu=\\\"x86\\\"")

  if (platform == "linux_arm64"):
    args_copy = args[:]
    args_copy.append("target_cpu=\\\"arm64\\\"")
    args_copy.append("v8_target_cpu=\\\"arm64\\\"")
    
  if (platform == "win_arm64"):
    args_copy = args[:]
    args_copy.append("target_cpu=\\\"arm64\\\"")
    args_copy.append("v8_target_cpu=\\\"arm64\\\"")
    args_copy.append("is_clang=false")
    
  if is_debug:
    args_copy.append("is_debug=true")
    if (platform == "windows"):
      args_copy.append("enable_iterator_debugging=true")
  else:
    args_copy.append("is_debug=false")
  
  linux_clang = False
  if platform == "linux":
    if "" != config.option("sysroot"):
      args_copy.append("use_sysroot=true")
      args_copy.append("is_clang=false")
      if is_ubuntu_24_or_higher():
        args_copy.append("use_gold=false")
      args_copy.append("sysroot=\\\"" + config.option("sysroot_linux_64") + "\\\"")
      args_copy.append("target_sysroot=\\\"" + config.option("sysroot_linux_64") + "\\\"")
    else:
      args_copy.append("is_clang=true")
      if "1" == config.option("use-clang"):
        linux_clang = True
      else:
        args_copy.append("use_sysroot=false")

  if platform == "linux_arm64":
    if "" != config.option("sysroot"):
      args_copy.append("use_sysroot=true")
      if is_ubuntu_24_or_higher():
        args_copy.append("use_gold=false")
      #args_copy.append("sysroot=\\\"" + config.option("sysroot_linux_64") + "\\\"")
      args_copy.append("target_sysroot=\\\"" + config.option("sysroot_linux_arm64") + "\\\"")
    else:
      args_copy.append("is_clang=true")
      if "1" == config.option("use-clang"):
        linux_clang = True
      else:
        args_copy.append("use_sysroot=false")


  if (platform == "windows"):
    args_copy.append("is_clang=false")

  if (platform == "mac") and base.is_os_arm():
    args_copy.append("host_cpu=\\\"x64\\\"")

  if linux_clang != True:
    args_copy.append("use_custom_libcxx=false")
    # v8's sandbox requires the hardened libc++ that use_custom_libcxx provides, and
    # says so itself:
    #   ERROR at //BUILD.gn:878:1: Assertion failed.
    #   assert(!v8_enable_sandbox || use_safe_libcxx,
    #   The sandbox requires libc++ hardening
    # v8_enable_sandbox defaults on for 64-bit, so asking for the system C++ library
    # without also turning the sandbox off makes `gn gen` refuse outright. We build
    # v8 as a monolithic static library to embed in doctrenderer, not as a browser
    # renderer, so the sandbox is not something we rely on here.
    args_copy.append("v8_enable_sandbox=false")

  # v8's DEPS pulls a Linux_x64 Rust toolchain regardless of host architecture, so
  # on aarch64 ninja gets eight steps in and dies with
  #   OSError: [Errno 8] Exec format error:
  #   PosixPath('../../third_party/rust-toolchain/bin/rustc')
  # confirmed by file(1): the fetched rustc is an x86-64 ELF. Same shape as the
  # x86-64 python bundle that check_python() used to force onto ARM hosts.
  #
  # Rust is not needed for what we build here - a monolithic static v8 embedded in
  # doctrenderer - so it is switched off rather than chasing an aarch64 toolchain
  # that v8's own DEPS does not offer.
  if base.is_os_arm() and (-1 != platform.find("linux")):
    args_copy.append("enable_rust=false")
    # Temporal is the only thing that pulls Rust in - v8's BUILD.gn has
    #   if (v8_enable_temporal_support) { public_deps = [ "//third_party/rust/temporal_capi" ] }
    # and that crate reaches rust_target(), which asserts enable_rust. So turning
    # Rust off without this gives a different and much less obvious failure:
    #   ERROR at //build/rust/gni_impl/rust_target.gni:43:3: assert(enable_rust)
    # naming only the template, four "whence" hops from temporal_capi.
    #
    # TRADE-OFF, stated rather than buried: this drops the Temporal date/time API
    # from the ARM Linux build. doctrenderer runs sdkjs, which targets a much
    # older JS baseline and does not use Temporal, so nothing we ship needs it -
    # but an x86 Linux build keeps it, so the two are not identical. Revisit if
    # v8 ever ships an aarch64 rustc, at which point both flags can go.
    args_copy.append("v8_enable_temporal_support=false")

    clang_prefix = system_clang_prefix()
    if clang_prefix is None:
      # The bundled clang is x86-64, so leaving gn on it here cannot work: it
      # surfaces only after the whole v8 fetch, as "Exec format error" (or, in
      # Docker Desktop, "rosetta error: failed to open elf at
      # /lib64/ld-linux-x86-64.so.2") on the first compile. Say why instead.
      print("v8: no usable system clang for linux arm64. Install clang, lld and "
            "compiler-rt (Ubuntu: libclang-rt-<N>-dev, which provides "
            "lib/linux/libclang_rt.builtins-aarch64.a under `clang -print-resource-dir`).")
      sys.exit(1)
    if clang_prefix is not None:
      args_copy.append("clang_base_path=\\\"" + clang_prefix[0] + "\\\"")
      args_copy.append("clang_version=\\\"" + clang_prefix[1] + "\\\"")
      # Chromium's own clang plugins (blink-gc-plugin and friends) ship only with
      # the bundled toolchain; asking a distro clang to load them fails the very
      # first compile with "unable to load plugin".
      args_copy.append("clang_use_chrome_plugins=false")

  return "--args=\"" + " ".join(args_copy) + "\""

def ninja_windows_make(args, is_64=True, is_debug=False, is_arm=False):
  directory_out = "out.gn/"
    
  if is_arm:
    directory_out += "win_arm64/"
  else:
    directory_out += ("win_64/" if is_64 else "win_32/")
    
  directory_out += ("debug" if is_debug else "release")

  if is_arm:
    base.cmd2("gn", ["gen", directory_out, make_args(args, "win_arm64", is_64, is_debug)])
  else:
    base.cmd2("gn", ["gen", directory_out, make_args(args, "windows", is_64, is_debug)])
    
  base.copy_file("./" + directory_out + "/obj/v8_wrappers.ninja", "./" + directory_out + "/obj/v8_wrappers.ninja.bak")
  base.replaceInFile("./" + directory_out + "/obj/v8_wrappers.ninja", "target_output_name = v8_wrappers", "target_output_name = v8_wrappers\nbuild obj/v8_wrappers.obj: cxx ../../../src/base/platform/wrappers.cc")
  base.replaceInFile("./" + directory_out + "/obj/v8_wrappers.ninja", "build obj/v8_wrappers.lib: alink", "build obj/v8_wrappers.lib: alink obj/v8_wrappers.obj")

  win_toolset_wrapper_file = "build/toolchain/win/tool_wrapper.py"
  win_toolset_wrapper_file_content = base.readFile("build/toolchain/win/tool_wrapper.py")
  if (-1 == win_toolset_wrapper_file_content.find("line = line.decode('utf8')")):
    base.replaceInFile(win_toolset_wrapper_file, "for line in link.stdout:\n", "for line in link.stdout:\n      line = line.decode('utf8')\n")


  base.cmd("ninja", ["-C", directory_out, "v8_wrappers"])
  if is_arm:
    base.copy_file('./' + directory_out + '/obj/v8_wrappers.lib', './' + directory_out + '/x64/obj/v8_wrappers.lib')
  base.cmd("ninja", ["-C", directory_out])
  base.delete_file("./" + directory_out + "/obj/v8_wrappers.ninja")
  base.move_file("./" + directory_out + "/obj/v8_wrappers.ninja.bak", "./" + directory_out + "/obj/v8_wrappers.ninja")
  return

# patch v8 for build ---------------------------------------------------
def patch_windows_debug():
  # v8 8.9 version does not built with enable_iterator_debugging flag
  # patch heap.h file:
  file_patch = "./src/heap/heap.h"
  base.copy_file(file_patch, file_patch + ".bak")
  content_old = base.readFile(file_patch)
  posStart = content_old.find("class StrongRootBlockAllocator {")
  posEnd = content_old.find("};", posStart + 1)
  posEnd = content_old.find("};", posEnd + 1)
  content = content_old[0:posStart]
  content += base.readFile("./../../../../../build_tools/scripts/core_common/modules/v8_89.patch")
  content += content_old[posEnd + 2:]
  base.writeFile(file_patch, content)
  return

def unpatch_windows_debug():
  file_patch = "./src/heap/heap.h"
  base.move_file(file_patch + ".bak", file_patch)
  return
# ----------------------------------------------------------------------

def gn_script_flags():
  """Tell gn which interpreter to run build scripts with.

  The gn revision 8.9 pins defaults exec_script's interpreter to a bare
  "python", and .gn does not override it, so on a distro that only ships
  python3 `gn gen` dies before generating anything:
    ERROR at //build/toolchain/concurrent_links.gni:84:19: Script returned
    non-zero exit code.
    Command: python .../build/toolchain/get_concurrent_links.py --mem_per_link_gb=3
    Returned 127.
  127 is "not found" - the script is fine, the interpreter is missing. The same
  setting is baked into every action gn writes for ninja, so this is not only a
  generate-time problem.

  Left alone where a `python` exists, so build machines that still have one are
  unaffected.
  """
  if ("windows" == base.host_platform()):
    return []
  if 0 == base.run_command("command -v python")["returncode"]:
    return []
  return ["--script-executable=" + sys.executable]

def cipd_ensure(package, version, root):
  """Install one CIPD package into root. depot_tools must already be on PATH."""
  base.create_dir(root)
  ensure_file = root + "/ensure_file.txt"
  base.writeFile(ensure_file, package + " " + version + "\n")
  base.cmd("cipd", ["ensure", "-ensure-file", ensure_file, "-root", root], True)
  return

def fix_ninja_arm64():
  """Provide a ninja binary for hosts where DEPS does not. Call from v8/.

  8.9's DEPS predates the ninja CIPD entry, so the build relied on a ninja
  copied out of the trunk third_party captured between "fetch v8" and the
  branch sync - and that copy only ever happens on the run that does the fetch.
  Without it depot_tools' wrapper stops the build:
    depot_tools/ninja.py: Could not find Ninja in the third_party of the
    current project, nor in your PATH.
  The wrapper looks for <solution>/third_party/ninja/ninja, so that is where
  this puts it, pinned rather than latest, and only when nothing usable is
  already there. An apt ninja-build would also satisfy the wrapper, but that is
  machine state invisible from the tree.
  """
  if not (base.is_os_arm() and "linux" == base.host_platform()):
    return
  if base.is_file("third_party/ninja/ninja"):
    return
  # Not `command -v ninja`: depot_tools is on PATH and ships a ninja *wrapper*,
  # so a bare existence check always succeeds and this would never run. Ask the
  # thing on PATH to do something instead - the wrapper fails, a real ninja does
  # not.
  if 0 == base.run_command("ninja --version")["returncode"]:
    return
  # The oldest 3pp ninja published for linux-arm64; 8.9 has no pin of its own.
  cipd_ensure("infra/3pp/tools/ninja/linux-arm64", "version:2@1.11.1.chromium.6",
              os.path.abspath("third_party/ninja"))
  return

def fix_gn_arm64():
  """Replace the x86-64 gn binary 8.9's DEPS pins with the arm64 build of the
  same revision. Call from the v8 checkout root.

  DEPS names the CIPD package by architecture rather than using ${platform}:
    'package': 'gn/gn/linux-amd64'
  so an aarch64 host ends up with an x86-64 gn at buildtools/linux64/gn and the
  build stops before generating anything:
    OSError: [Errno 8] Exec format error: '.../v8/buildtools/linux64/gn'
  Fourth in the same family as the bundled python, rustc and clang.

  gn/gn/linux-arm64 exists at the exact pinned revision (registered the same day
  as the amd64 one), so this stays on the pin rather than pulling a newer gn.
  """
  if not (base.is_os_arm() and "linux" == base.host_platform()):
    return

  gn_path = "buildtools/linux64/gn"
  if not base.is_file(gn_path):
    return
  if 0 == base.run_command("./" + gn_path + " --version")["returncode"]:
    return

  version_match = re.search(r"'gn_version'\s*:\s*'([^']+)'", base.readFile("DEPS"))
  if not version_match:
    return

  root = os.path.abspath("buildtools/gn-linux-arm64")
  cipd_ensure("gn/gn/linux-arm64", version_match.group(1), root)

  if base.is_file(root + "/gn"):
    base.copy_file(root + "/gn", gn_path)
    base.cmd("chmod", ["+x", gn_path], True)
  return

def v8_pinned_branch():
  """The v8 branch the rest of this module is written against.

  doctrenderer compiles against the 8.9 C++ API (9.9 on mac), so an unpinned
  checkout is not "a newer v8", it is a tree that cannot build at all.
  """
  if ("mac" == base.host_platform()):
    return "remotes/branch-heads/9.9"
  return "remotes/branch-heads/8.9"

def is_v8_pinned():
  """True when v8/ is checked out at exactly the pinned branch head."""
  branch = v8_pinned_branch()
  head = base.run_command("git -C v8 rev-parse HEAD")
  want = base.run_command("git -C v8 rev-parse " + branch)
  if 0 != head["returncode"] or 0 != want["returncode"]:
    return False
  return head["stdout"] == want["stdout"]

def make():
  old_env = dict(os.environ)
  old_cur = os.getcwd()

  base_dir = base.get_script_dir() + "/../../core/Common/3dParty/v8_89"
  if not base.is_dir(base_dir):
    base.create_dir(base_dir)

  if ("mac" == base.host_platform()):
    base.cmd("git", ["config", "--global", "http.postBuffer", "157286400"], True)

  os.chdir(base_dir)
  base.common_check_version("v8", "1", clean)
    
  if not base.is_dir("depot_tools"):
    base.cmd("git", ["clone", "https://chromium.googlesource.com/chromium/tools/depot_tools.git"])
    change_bootstrap()

  os.environ["PATH"] = base_dir + "/depot_tools" + os.pathsep + os.environ["PATH"]

  # depot_tools has to be initialised BEFORE anything uses it. fetch/gclient both
  # need the bundled python and the CIPD client, and a fresh clone has neither -
  # they announce it themselves:
  #   python3_bin_reldir.txt not found. need to initialize depot_tools by
  #   running gclient, update_depot_tools or ensure_bootstrap.
  # This call used to sit at the END of the fetch block, after "./depot_tools/fetch
  # v8" had already run and failed, so on a fresh tree fetch never produced a v8
  # directory and the build then died on os.chdir("v8") with a bare
  # FileNotFoundError - several steps away from the actual cause.
  if ("linux" == base.host_platform()):
    if not base.is_file("./depot_tools/python3_bin_reldir.txt"):
      base.cmd_in_dir("./depot_tools", "./ensure_bootstrap", [], True)

  if ("windows" == base.host_platform()):
    base.set_env("DEPOT_TOOLS_WIN_TOOLCHAIN", "0")
    base.set_env("GYP_MSVS_VERSION", config.option("vs-version"))

  if not base.is_dir("v8"):
    base.cmd("./depot_tools/fetch", ["v8"], True)
    base.copy_dir("./v8/third_party", "./v8/third_party_new")
    if ("windows" == base.host_platform()):
      os.chdir("v8")
      base.cmd("git", ["config", "--system", "core.longpaths", "true"], True)
      os.chdir("../")

  # The pin used to sit inside the "v8 does not exist yet" branch above, so it ran
  # exactly once - on the first fetch - and every later run trusted whatever was
  # there. "fetch v8" leaves the checkout on trunk, so if the sync that follows it
  # fails or is interrupted (a dropped connection, a full disk, ^C), the directory
  # still exists and the pin is never attempted again: the tree stays on trunk and
  # silently builds the wrong v8. That is what the ARM box was doing - a checkout
  # calling itself v8_89 with V8_MAJOR_VERSION 15 in include/v8-version.h, and a
  # build/ from the same week, which is why ninja was passing clang flags no
  # released compiler has ever heard of:
  #   clang++: error: unknown argument: '-fdiagnostics-show-inlining-chain'
  # Checking the checkout rather than the directory makes this self-healing.
  if not is_v8_pinned():
    base.cmd("./depot_tools/gclient", ["sync", "-r", v8_pinned_branch()], True)
    base.cmd("gclient", ["sync", "--force"], True)

  # 8.9's DEPS predates the ninja entry, so the binary comes from the trunk
  # third_party captured just after fetch.
  if base.is_dir("./v8/third_party_new/ninja") and not base.is_dir("./v8/third_party/ninja"):
    base.copy_dir("./v8/third_party_new/ninja", "./v8/third_party/ninja")

  if ("windows" == base.host_platform()):
    base.replaceInFile("v8/build/config/win/BUILD.gn", ":static_crt", ":dynamic_crt")
    
    # fix for new depot_tools and vs2019, as VC folder contains a folder with a symbol in the name
    # sorting is done by increasing version, so 0 is a dummy value
    replace_src = "  def to_int_if_int(x):\n    try:\n      return int(x)\n    except ValueError:\n      return x"
    replace_dst = "  def to_int_if_int(x):\n    try:\n      return int(x)\n    except ValueError:\n      return 0"
    base.replaceInFile("v8/build/vs_toolchain.py", replace_src, replace_dst)
    
    
    if not base.is_file("v8/src/base/platform/wrappers.cc"):
      base.writeFile("v8/src/base/platform/wrappers.cc", "#include \"src/base/platform/wrappers.h\"\n")
  
    if config.check_option("platform", "win_arm64"):
      base.replaceInFile("v8/build/toolchain/win/setup_toolchain.py", "SDK_VERSION = \'10.0.26100.0\'", "SDK_VERSION = \'10.0.22621.0\'")
  else:
    base.replaceInFile("depot_tools/gclient_paths.py", "@functools.lru_cache", "")

  if ("mac" == base.host_platform()):
    if not base.is_file("v8/build/config/compiler/BUILD.gn.bak"):
      base.copy_file("v8/build/config/compiler/BUILD.gn", "v8/build/config/compiler/BUILD.gn.bak")
      base.replaceInFile("v8/build/config/compiler/BUILD.gn", "\"-Wloop-analysis\",", "\"-Wloop-analysis\", \"-D_Float16=short\",")

  # 2021 v8 against a 2024 toolchain needs two flags, and neither failure names
  # a flag or a header.
  #
  # libstdc++ 13 stopped including <cstdint> from other headers, and this v8
  # leans on that having happened, so the first file ninja compiles produces 15
  # errors of the form
  #   ../../src/base/logging.h:176:34: error: use of undeclared identifier 'uint8_t'
  #   ../../src/base/bits.h:...: error: unknown type name 'intptr_t'; did you mean '__intptr_t'?
  #
  # clang 16 turned -Wenum-constexpr-conversion into an error-by-default, which
  # v8's bit-field.h trips on every enum-typed field:
  #   ../../src/base/bit-field.h:43:29: error: integer value 7 is outside the
  #   valid range of values [0, 3] for the enumeration type 'Kind'
  # treat_warnings_as_errors=false does not reach it - it is an error, not a
  # warning promoted to one - so it has to be named explicitly. clang 20 removes
  # the escape hatch, at which point this needs a real source fix or an older
  # clang.
  #
  # This tree has no extra_cflags gn arg to hang either on (checked with
  # `gn args --list`), so they go into config("compiler") itself, right after
  # cflags_cc is initialised so later += still apply. Written against the
  # pristine file each time rather than appending to whatever is there.
  if ("linux" == base.host_platform()):
    compiler_gn = "v8/build/config/compiler/BUILD.gn"
    compiler_gn_bak = compiler_gn + ".rd-bak"
    cflags_cc = "[ \"-include\", \"cstdint\", \"-Wno-enum-constexpr-conversion\" ]"
    if -1 == base.readFile(compiler_gn).find(cflags_cc):
      if base.is_file(compiler_gn_bak):
        base.copy_file(compiler_gn_bak, compiler_gn)
      else:
        base.copy_file(compiler_gn, compiler_gn_bak)
      base.replaceInFile(compiler_gn,
                         "config(\"compiler\") {\n  asmflags = []\n  cflags = []\n  cflags_c = []\n  cflags_cc = []",
                         "config(\"compiler\") {\n  asmflags = []\n  cflags = []\n  cflags_c = []\n  cflags_cc = " + cflags_cc)

  # Guarded on the file's contents, not on the .bak marker it used to check.
  # The marker survives a re-sync while the file it describes does not, so after
  # gclient put the 8.9 jinja2 back, the patch was skipped and ninja died 159
  # steps in on a python2 import:
  #   from collections import Mapping
  #   ImportError: cannot import name 'Mapping' from 'collections'
  # Same shape as the v8 pin that only ran on first fetch: a marker standing in
  # for the state it is meant to describe.
  #
  # The match is the UNINDENTED import line only. The replacement keeps
  # "from collections import Mapping" as its indented fallback, so a plain
  # substring test matched our own output and every re-run wrapped the import
  # in one more try: block - the second run died with
  #   IndentationError: expected an indented block after 'try' statement
  # A tree already damaged that way is put back from the .bak first.
  jinja_tests = "v8/third_party/jinja2/tests.py"
  if base.is_file(jinja_tests):
    if -1 != base.readFile(jinja_tests).find("    try:\n    from collections.abc") and base.is_file(jinja_tests + ".bak"):
      base.copy_file(jinja_tests + ".bak", jinja_tests)
    jinja_src = base.readFile(jinja_tests)
    if re.search(r"^from collections import Mapping$", jinja_src, re.M):
      if not base.is_file(jinja_tests + ".bak"):
        base.copy_file(jinja_tests, jinja_tests + ".bak")
      jinja_src = re.sub(r"^from collections import Mapping$",
                         "try:\n    from collections.abc import Mapping\nexcept ImportError:\n    from collections import Mapping",
                         jinja_src, count=1, flags=re.M)
      base.writeFile(jinja_tests, jinja_src)

  os.chdir("v8")

  is_ubuntu24 = is_ubuntu_24_or_higher()
  fix_ubuntu24()
  fix_gn_arm64()
  fix_ninja_arm64()
  
  gn_args = ["v8_static_library=true",
             "is_component_build=false",
             "v8_monolithic=true",
             "v8_use_external_startup_data=false",
             "treat_warnings_as_errors=false"]

  if config.check_option("platform", "linux_64"):
    if config.option("sysroot") != "":
      sysroot_path = config.option("sysroot_linux_64")
      sysroot_path_bin = config.get_custom_sysroot_bin("linux_64")

      old_env = dict(os.environ)
      base.set_sysroot_env("linux_64")

      pkg_old = os.environ.get("PKG_CONFIG_PATH", "")
      os.environ["PKG_CONFIG_PATH"] = sysroot_path + "/usr/lib/x86_64-linux-gnu/pkgconfig:" + sysroot_path + "/usr/lib/pkgconfig:" + sysroot_path + "/usr/share/pkgconfig"
      base.cmd2("gn", ["gen", "out.gn/linux_64"] + gn_script_flags() + [make_args(gn_args, "linux")], False)
      os.environ["PKG_CONFIG_PATH"] = pkg_old

      base.cmd2("ninja", ["-C", "out.gn/linux_64"], False)
      base.restore_sysroot_env()
    else:
      base.cmd2("gn", ["gen", "out.gn/linux_64"] + gn_script_flags() + [make_args(gn_args, "linux")], False)
      base.cmd2("ninja", ["-C", "out.gn/linux_64"], False)


  if config.check_option("platform", "linux_32"):
    base.cmd2("gn", ["gen", "out.gn/linux_32"] + gn_script_flags() + [make_args(gn_args, "linux", False)])
    base.cmd("ninja", ["-C", "out.gn/linux_32"])

  if config.check_option("platform", "linux_arm64"):
    # 8.9-era chromium scripts carry a "#!/usr/bin/env python" shebang, and no
    # distro has shipped a bare `python` since 20.04:
    #   /usr/bin/env: 'python': No such file or directory
    #   Error (build/linux/sysroot_scripts/install-sysroot.py): 127
    # gclient's own hooks get away with it because gclient injects a python shim
    # onto PATH for the duration of a hook; calling the script directly does not.
    base.cmd(sys.executable, ["build/linux/sysroot_scripts/install-sysroot.py", "--arch=arm64"], False)
    
    sysroot_path = config.option("sysroot_linux_64")
    pkg_old = os.environ.get("PKG_CONFIG_PATH", "")
    os.environ["PKG_CONFIG_PATH"] = sysroot_path + "/usr/lib/x86_64-linux-gnu/pkgconfig:" + sysroot_path + "/usr/lib/pkgconfig:" + sysroot_path + "/usr/share/pkgconfig"
    base.cmd2("gn", ["gen", "out.gn/linux_arm64"] + gn_script_flags() + [make_args(gn_args, "linux_arm64", False)])
    os.environ["PKG_CONFIG_PATH"] = pkg_old

    base.cmd("ninja", ["-C", "out.gn/linux_arm64"])

  if config.check_option("platform", "mac_64"):
    base.cmd2("gn", ["gen", "out.gn/mac_64", make_args(gn_args, "mac")])
    base.cmd("ninja", ["-C", "out.gn/mac_64"])
    
  if config.check_option("platform", "win_arm64") and not base.is_file("out.gn/win_arm64/release/obj/v8_monolith.lib"):
    ninja_windows_make(gn_args, True, False, True)

  if config.check_option("platform", "win_64"):
    if (-1 != config.option("config").lower().find("debug")):
      if not base.is_file("out.gn/win_64/debug/obj/v8_monolith.lib"):
        patch_windows_debug()
        ninja_windows_make(gn_args, True, True)
        unpatch_windows_debug()

    if not base.is_file("out.gn/win_64/release/obj/v8_monolith.lib"):
      ninja_windows_make(gn_args)

  if config.check_option("platform", "win_32"):
    if (-1 != config.option("config").lower().find("debug")):
      if not base.is_file("out.gn/win_32/debug/obj/v8_monolith.lib"):
        patch_windows_debug()
        ninja_windows_make(gn_args, False, True)
        unpatch_windows_debug()

    if not base.is_file("out.gn/win_32/release/obj/v8_monolith.lib"):
      ninja_windows_make(gn_args, False)

  os.chdir(old_cur)
  os.environ.clear()
  os.environ.update(old_env)
