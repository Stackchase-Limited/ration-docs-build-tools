#!/usr/bin/env python3
"""Replace duplicate help media in a packaged payload with relative symlinks.

The offline help ships the same screenshots and animations under every language
directory: only the surrounding HTML is translated, the images are byte-identical.
In a 9.4 desktop payload that is the single largest item - one 15 MB GIF
(`cellvalueformula.gif`) appears once per language, and the help tree as a whole is
larger than the Chromium framework.

This replaces every duplicate with a relative symlink to one canonical copy, so the
bytes are stored once. Nothing is deleted and no HTML is rewritten: every path that
resolved before still resolves, to identical content, which is what `--verify`
asserts.

Only regular files are considered, only the media extensions below, and only those
at least --min-size bytes. Symlinks are relative, so the payload stays relocatable.

  python3 dedupe_help_images.py <payload> --dry-run    # report, change nothing
  python3 dedupe_help_images.py <payload>              # deduplicate
  python3 dedupe_help_images.py <payload> --verify     # check every link resolves
"""
import argparse
import hashlib
import os
import sys

MEDIA_EXTENSIONS = {'.gif', '.png', '.jpg', '.jpeg', '.svg', '.webp', '.mp4', '.ico'}


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def help_media(root, min_size):
    """Every regular media file under a help/ directory, at least min_size bytes."""
    for dirpath, _dirnames, filenames in os.walk(root):
        if os.sep + 'help' + os.sep not in dirpath + os.sep:
            continue
        for name in filenames:
            if os.path.splitext(name)[1].lower() not in MEDIA_EXTENSIONS:
                continue
            path = os.path.join(dirpath, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            if os.path.getsize(path) >= min_size:
                yield path


def human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if abs(n) < 1024:
            return '%.1f %s' % (n, unit)
        n /= 1024.0
    return '%.1f TB' % n


def dedupe(root, min_size, dry_run):
    # Group by size first, so only same-size files are ever hashed.
    by_size = {}
    for path in help_media(root, min_size):
        by_size.setdefault(os.path.getsize(path), []).append(path)

    saved = 0
    linked = 0
    groups = 0
    for size, paths in sorted(by_size.items()):
        if len(paths) < 2:
            continue
        by_hash = {}
        for path in sorted(paths):
            by_hash.setdefault(file_hash(path), []).append(path)
        for _digest, same in by_hash.items():
            if len(same) < 2:
                continue
            groups += 1
            canonical = same[0]
            for duplicate in same[1:]:
                target = os.path.relpath(canonical, os.path.dirname(duplicate))
                if not dry_run:
                    tmp = duplicate + '.dedupe-tmp'
                    os.symlink(target, tmp)
                    os.replace(tmp, duplicate)
                saved += size
                linked += 1

    return {'groups': groups, 'links': linked, 'saved': saved}


def verify(root):
    """Every symlink under help/ must resolve, and to a regular file."""
    broken = []
    checked = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        if os.sep + 'help' + os.sep not in dirpath + os.sep:
            continue
        for name in filenames:
            path = os.path.join(dirpath, name)
            if not os.path.islink(path):
                continue
            checked += 1
            resolved = os.path.realpath(path)
            if not os.path.isfile(resolved):
                broken.append(path)
    return checked, broken


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('payload')
    ap.add_argument('--min-size', type=int, default=65536)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--verify', action='store_true')
    args = ap.parse_args()

    if not os.path.isdir(args.payload):
        sys.stderr.write('not a directory: %s\n' % args.payload)
        return 2

    if args.verify:
        checked, broken = verify(args.payload)
        print('  %d symlinks checked, %d broken' % (checked, len(broken)))
        for path in broken[:20]:
            print('    BROKEN: %s' % path)
        return 1 if broken else 0

    result = dedupe(args.payload, args.min_size, args.dry_run)
    print('  %s%d duplicate groups, %d files linked, %s saved'
          % ('[dry run] ' if args.dry_run else '', result['groups'],
             result['links'], human(result['saved'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
