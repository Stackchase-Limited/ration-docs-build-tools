#!/usr/bin/env python3
"""
Check that every module we ship can resolve the symbols it imports from our own
other modules.  ONLYOFFICE/DesktopEditors#2445.

That issue is a launch-time abort with

    The procedure entry point ?Encode@CBase64Converter@NSFile@@SA_NPEAEHAEAPEADAEAHK@Z
    could not be located in the dynamic link library ...\\ooxmlsignature.dll

`PEAE` in that mangled name is a non-const `BYTE*`.  core commit a84491cf74
(2025-07-10) changed CBase64Converter::Encode's first parameter to `const BYTE*`,
which changes the mangled name - so the shipped ooxmlsignature.dll had been built
against a header older than the kernel it was packaged with.  Nothing in the build
noticed; the mismatch only surfaced on a user's machine, as a dialog and an exit.

This is cheap to catch at package time.  For every module in the payload we take
the symbols it imports and the symbols the payload as a whole exports, and report
any import that belongs to one of *our* namespaces but that nothing in the payload
defines.  Restricting it to our own namespaces is what keeps it quiet: symbols
that come from the C library, libstdc++, Qt, ICU or the system frameworks are
resolved by the loader from outside the payload and are none of our business.

  usage: check_symbol_closure.py <payload-dir> [--verbose]
  exit 0 = closed, exit 1 = at least one of our imports is unresolved.
"""

import os
import re
import subprocess
import sys

# Top-level namespaces that are shared by us and by the toolchain; an unresolved
# import here means a system library supplies it, not that we dropped something.
FOREIGN = {
    'std', '__gnu_cxx', '__cxxabiv1', 'boost', 'google', 'v8', 'icu',
    'absl', 'cef', 'Cef', 'testing', 'QT', 'Qt', 'zip', 'nlohmann',
}

MACHO = sys.platform == 'darwin'


def is_module(path):
    if os.path.islink(path) or not os.path.isfile(path):
        return False
    try:
        with open(path, 'rb') as f:
            magic = f.read(4)
    except OSError:
        return False
    if magic[:4] == b'\x7fELF':
        return True
    return magic in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe',
                     b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca')


def nm(args, path):
    try:
        out = subprocess.run(['nm'] + args + [path], capture_output=True,
                             text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return []
    return out.stdout.splitlines()


def imports(path):
    if MACHO:
        lines = nm(['-u'], path)
        return {ln.strip() for ln in lines if ln.strip().startswith('_')}
    out = set()
    for ln in nm(['-D', '--undefined-only'], path):
        parts = ln.split()
        if parts:
            out.add(parts[-1].split('@')[0])
    return out


def exports(path):
    out = set()
    if MACHO:
        for ln in nm(['-gU'], path):
            parts = ln.split()
            if len(parts) >= 3 and parts[-2] in ('T', 'D', 'B', 'S', 'W', 'R'):
                out.add(parts[-1])
        return out
    for ln in nm(['-D', '--defined-only'], path):
        parts = ln.split()
        if len(parts) >= 3:
            out.add(parts[-1].split('@')[0])
    return out


# Only nested names - `_ZN<len><name>...` - carry a namespace or class qualifier.
# An unqualified free function (`_Z20de265_cond_broadcast...`) has none, and
# treating its name as a namespace would both inflate the set and risk matching an
# unrelated system symbol that happens to share a first component.
_ITANIUM = re.compile(r'^_?_Z(?:T[VTIS])?N(\d+)(\w+)')


def top_level(symbol):
    """First namespace or class component of a C++ symbol, or None if unqualified."""
    m = _ITANIUM.match(symbol)
    if not m:
        return None
    n = int(m.group(1))
    name = m.group(2)[:n]
    return name if len(name) == n else None


def check(root):
    """Return [(module, namespace, symbol)] for imports of ours nothing defines.

    Raises ValueError if `root` holds no modules at all, so a caller cannot read
    an empty result as a clean payload.
    """
    modules = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            p = os.path.join(dirpath, name)
            if is_module(p):
                modules.append(p)
    if not modules:
        raise ValueError('no modules found under %s' % root)

    defined = set()
    per_module = {}
    for p in modules:
        defined |= exports(p)
        per_module[p] = imports(p)

    # Namespaces the payload itself defines - those are the ones we own.
    ours = {top_level(s) for s in defined}
    ours.discard(None)
    ours -= FOREIGN

    failures = []
    for p, undef in sorted(per_module.items()):
        for s in sorted(undef):
            if s in defined:
                continue
            ns = top_level(s)
            if ns is not None and ns in ours:
                failures.append((os.path.relpath(p, root), ns, s))

    check.last_stats = (len(modules), len(defined), len(ours))
    return failures



def dependencies(path):
    """Libraries this module asks the loader for, by basename."""
    out = set()
    if MACHO:
        try:
            r = subprocess.run(['otool', '-L', path], capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            return out
        for ln in r.stdout.splitlines()[1:]:
            ln = ln.strip()
            if not ln:
                continue
            name = ln.split(' ')[0]
            out.add(os.path.basename(name.split('/')[-1]))
        return out
    try:
        r = subprocess.run(['objdump', '-p', path], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return out
    for ln in r.stdout.splitlines():
        ln = ln.strip()
        if ln.startswith('NEEDED'):
            out.add(ln.split()[-1])
    return out


def check_libraries(root):
    """Return [(module, dependency)] for Qt libraries we ship a family of but not this one.

    ONLYOFFICE/DesktopEditors#2274: qt_copy_plugin copies a plugin directory wholesale
    while the Qt libraries are an explicit list, so the payload shipped a virtual
    keyboard plugin needing QtQml, QtQmlModels, QtQuick and QtVirtualKeyboard - none of
    them bundled. On a machine with system Qt5 the loader satisfies those from the
    system, they link the system QtCore, and the process ends up holding two QtCores.

    Restricted to Qt because Qt is the one framework this payload bundles wholesale and
    must therefore bundle completely; everything else is deliberately taken from the
    system and is not ours to resolve.
    """
    shipped = set()
    modules = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            p = os.path.join(dirpath, name)
            shipped.add(name)
            if is_module(p):
                modules.append(p)
                # A framework's binary has no extension; record its bundle name too.
                shipped.add(os.path.basename(os.path.dirname(dirpath)).replace('.framework', ''))

    def isQt(dep):
        base = dep.replace('lib', '', 1) if dep.startswith('lib') else dep
        return base.startswith('Qt')

    failures = []
    for p in sorted(modules):
        for dep in sorted(dependencies(p)):
            if not isQt(dep):
                continue
            stem = dep.replace('lib', '', 1) if dep.startswith('lib') else dep
            stem = stem.split('.')[0]
            if stem in shipped or dep in shipped:
                continue
            failures.append((os.path.relpath(p, root), dep))
    return failures

def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 2
    root = argv[0]
    verbose = '--verbose' in argv
    if not os.path.isdir(root):
        sys.stderr.write('not a directory: %s\n' % root)
        return 2

    try:
        failures = check(root)
    except ValueError as e:
        sys.stderr.write('%s\n' % e)
        return 2

    nmod, ndef, nns = check.last_stats
    print('checked %d modules, %d exported symbols, %d namespaces of ours'
          % (nmod, ndef, nns))

    libs = check_libraries(root)
    if libs:
        print('\n%d Qt library dependencie(s) the payload does not ship:' % len(libs))
        for mod, dep in libs:
            print('  %s\n      needs %s' % (mod, dep))
        print('\nThis is the #2274 failure mode: a plugin copied in wholesale whose Qt\n'
              'libraries are not on the explicit list. It cannot load from the bundle, and\n'
              'on a machine with system Qt it loads a second copy of Qt into the process.')

    if not failures and not libs:
        print('ok - every import of ours is satisfied inside the payload')
        return 0
    if not failures:
        return 1

    print('\n%d unresolved import(s) of our own symbols:' % len(failures))
    for mod, ns, s in failures:
        print('  %s\n      wants %s::... %s' % (mod, ns, s))
    print('\nThis is the #2445 failure mode: a module built against a different '
          'revision\nof a header than the module that defines the symbol. Rebuild '
          'the payload from\na clean tree rather than reusing prebuilt output.')
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
