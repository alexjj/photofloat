"""Naming of cache files and small helpers shared by the scanner.

The cache file names must match the ones computed by web/js/photofloat.js,
so keep the two in sync.
"""

import os
import sys
from datetime import datetime

DATE_FORMAT = "%a %b %d %H:%M:%S %Y"

_level = -1


def message(category, text):
    sep = "  " if _level <= 0 else "--"
    print(
        "%s %s%s[%s]%s%s"
        % (
            datetime.now().replace(microsecond=0).isoformat(),
            max(0, _level) * "  |",
            sep,
            category,
            max(1, 14 - len(category)) * " ",
            text,
        ),
        flush=True,
    )


def next_level():
    global _level
    _level += 1


def back_level():
    global _level
    _level -= 1


def cache_name(path):
    """Turn a relative album/photo path into a flat cache file name stem."""
    path = path.strip("/")
    if not path:
        return "root"
    path = path.replace("/", "-").replace(" ", "_")
    for char in "()&,#[]\"'":
        path = path.replace(char, "")
    path = path.replace("_-_", "-").lower()
    while "--" in path:
        path = path.replace("--", "-")
    while "__" in path:
        path = path.replace("__", "_")
    return path


def _media_base(path):
    # Files directly in the root album get a "root-" prefix so they can
    # never collide with an album's JSON file.
    if "/" not in path.strip("/"):
        path = "root-" + path
    return cache_name(path)


def json_cache(path):
    return cache_name(path) + ".json"


def image_cache(path, size, square=False):
    return "%s_%d%s.jpg" % (_media_base(path), size, "s" if square else "")


def video_cache(path):
    return _media_base(path) + ".mp4"


def file_mtime(path):
    return datetime.fromtimestamp(int(os.path.getmtime(path)))


def relative_path(path, base):
    path = os.path.relpath(path, base)
    if path == ".":
        return ""
    if os.sep != "/":
        path = path.replace(os.sep, "/")
    return path


def fs_safe(name):
    """Return False for names the filesystem could not decode as text."""
    try:
        name.encode(sys.getfilesystemencoding())
    except UnicodeEncodeError:
        return False
    return True
