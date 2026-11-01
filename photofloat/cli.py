"""Command line interface.

    photofloat scan     # scan albums and (re)build the cache
    photofloat serve    # preview the site at http://localhost:8000
"""

import argparse
import os
import sys

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None

from . import __version__
from .cachepath import message

DEFAULTS = {
    "site": "web",
    "albums": None,  # default: <site>/albums
    "cache": None,  # default: <site>/cache
    "title": "Photos",
    # Longest side, in pixels, of the photos shown in the viewer. The page
    # picks the smallest one that is sharp on the visitor's screen.
    "photo_sizes": [1280, 2048, 3840],
    # Square thumbnails: 150 for normal screens, 300 for high-DPI screens.
    "thumb_sizes": [150, 300],
    "quality": 85,
    # Short side of transcoded videos, in pixels.
    "video_size": 1080,
    "download_originals": True,
    "jobs": 0,  # 0 = all CPU cores
    "port": 8000,
}


def load_config(path):
    if path is None:
        path = "photofloat.toml" if os.path.exists("photofloat.toml") else None
        if path is None:
            return {}
    if tomllib is None:
        sys.exit("Reading %s needs Python 3.11 or newer." % path)
    try:
        with open(path, "rb") as fp:
            config = tomllib.load(fp)
    except OSError as e:
        sys.exit("Can't read config file %s: %s" % (path, e))
    except tomllib.TOMLDecodeError as e:
        sys.exit("Error in config file %s: %s" % (path, e))
    unknown = set(config) - set(DEFAULTS)
    if unknown:
        sys.exit("Unknown setting(s) in %s: %s" % (path, ", ".join(sorted(unknown))))
    return config


def build_options(args):
    options = dict(DEFAULTS)
    options.update(load_config(args.config))
    for key in DEFAULTS:
        value = getattr(args, key, None)
        if value is not None:
            options[key] = value
    if options["albums"] is None:
        options["albums"] = os.path.join(options["site"], "albums")
    if options["cache"] is None:
        options["cache"] = os.path.join(options["site"], "cache")
    if not options["jobs"] or options["jobs"] < 1:
        options["jobs"] = os.cpu_count() or 1
    for key in ("photo_sizes", "thumb_sizes"):
        sizes = sorted({int(s) for s in options[key]})
        if not sizes or sizes[0] < 16:
            sys.exit("%s must be a list of pixel sizes" % key)
        options[key] = sizes
    if not 1 <= int(options["quality"]) <= 100:
        sys.exit("quality must be between 1 and 100")
    return options


def sizes(value):
    try:
        return [int(v) for v in value.split(",") if v.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError("expected a comma separated list of numbers, e.g. 1280,2048,3840")


def cmd_scan(args):
    from .media import ffmpeg_available
    from .scanner import TreeWalker

    # Old usage: photofloat scan ALBUM_PATH CACHE_PATH
    if args.paths:
        if len(args.paths) != 2:
            sys.exit("usage: photofloat scan [ALBUM_PATH CACHE_PATH]")
        args.albums, args.cache = args.paths
    options = build_options(args)
    if not os.path.isdir(options["albums"]):
        sys.exit(
            "Album folder %s does not exist. Put your photos there (one folder per album),\n"
            "or point to them with --albums or the 'albums' setting in photofloat.toml."
            % options["albums"]
        )
    if not ffmpeg_available():
        message("warning", "ffmpeg not found, videos will be skipped")
    os.umask(0o022)
    try:
        TreeWalker(options["albums"], options["cache"], options)
    except KeyboardInterrupt:
        message("keyboard", "CTRL+C pressed, quitting.")
        sys.exit(130)


def cmd_serve(args):
    from .server import serve

    options = build_options(args)
    serve(options["site"], options["port"], args.bind, options["albums"], options["cache"])


def main(argv=None):
    parser = argparse.ArgumentParser(prog="photofloat", description="Static web photo gallery.")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    parser.add_argument("-c", "--config", help="config file (default: ./photofloat.toml if present)")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--site", help="web site folder (default: web)")
        p.add_argument("--albums", help="folder with your photos (default: <site>/albums)")
        p.add_argument("--cache", help="folder for generated files (default: <site>/cache)")

    scan = sub.add_parser("scan", help="scan albums and update the cache")
    common(scan)
    scan.add_argument("paths", nargs="*", help=argparse.SUPPRESS)
    scan.add_argument("--title", help="gallery title shown on the page")
    scan.add_argument("--photo-sizes", type=sizes, dest="photo_sizes",
                      help="photo sizes in pixels, e.g. 1280,2048,3840")
    scan.add_argument("--thumb-sizes", type=sizes, dest="thumb_sizes",
                      help="square thumbnail sizes in pixels, e.g. 150,300")
    scan.add_argument("--quality", type=int, help="JPEG quality, 1-100 (default 85)")
    scan.add_argument("--video-size", type=int, dest="video_size",
                      help="short side of transcoded videos in pixels (default 1080)")
    scan.add_argument("--no-download-originals", action="store_false", dest="download_originals",
                      default=None, help="hide the 'download original' link")
    scan.add_argument("-j", "--jobs", type=int, help="parallel workers (default: all CPU cores)")
    scan.set_defaults(func=cmd_scan)

    serve = sub.add_parser("serve", help="preview the site locally")
    common(serve)
    serve.add_argument("-p", "--port", type=int, help="port (default 8000)")
    serve.add_argument("--bind", default="127.0.0.1", help="address to listen on (default 127.0.0.1)")
    serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
