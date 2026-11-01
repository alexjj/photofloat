"""Walks the album directory tree and keeps the cache directory up to date."""

import json
import os
from concurrent.futures import ProcessPoolExecutor

from .cachepath import (
    back_level,
    file_mtime,
    fs_safe,
    json_cache,
    message,
    next_level,
    relative_path,
)
from .media import Album, Photo, PhotoAlbumEncoder, media_type_for, process_media

OPTIONS_FILE = "options.json"
# Bump when the cache format changes in a way that needs a full rebuild.
CACHE_VERSION = 2


class TreeWalker:
    def __init__(self, album_path, cache_path, options):
        self.album_path = os.path.abspath(album_path)
        self.cache_path = os.path.abspath(cache_path)
        self.options = options
        self.all_albums = []
        self.all_photos = []
        os.makedirs(self.cache_path, exist_ok=True)

        # If image sizes changed since the last scan, the "directory hasn't
        # changed" shortcut can't be trusted: every photo must be checked.
        self.trust_cache = self._previous_options_match()

        with ProcessPoolExecutor(max_workers=options["jobs"]) as pool:
            self.pool = pool
            self.walk(self.album_path)
        self.write_options()
        self.big_lists()
        self.remove_stale()
        message("complete", "%d albums, %d photos and videos" % (len(self.all_albums), len(self.all_photos)))

    def _cache_options(self):
        return {
            "version": CACHE_VERSION,
            "thumbSizes": sorted(self.options["thumb_sizes"]),
            "photoSizes": sorted(self.options["photo_sizes"]),
            "videoSize": self.options["video_size"],
            "quality": self.options["quality"],
        }

    def _previous_options_match(self):
        try:
            with open(os.path.join(self.cache_path, OPTIONS_FILE), encoding="utf-8") as fp:
                previous = json.load(fp)
        except (OSError, ValueError):
            return False
        current = self._cache_options()
        return all(previous.get(key) == value for key, value in current.items())

    def write_options(self):
        options = self._cache_options()
        options.update({
            "title": self.options["title"],
            "downloadOriginals": self.options["download_originals"],
        })
        with open(os.path.join(self.cache_path, OPTIONS_FILE), "w", encoding="utf-8") as fp:
            json.dump(options, fp, ensure_ascii=False)

    def _caches_exist(self, photo):
        return all(os.path.exists(os.path.join(self.cache_path, c)) for c in photo.caches(self.options))

    def walk(self, path):
        next_level()
        try:
            return self._walk(path)
        finally:
            back_level()

    def _walk(self, path):
        name = os.path.basename(path) or path
        if not os.access(path, os.R_OK | os.X_OK):
            message("access denied", name)
            return None
        message("walking", name)
        rel_path = relative_path(path, self.album_path)
        cache = os.path.join(self.cache_path, json_cache(rel_path))
        cached_album = None
        fully_cached = False
        if os.path.exists(cache):
            try:
                cached_album = Album.from_cache(cache)
                if self.trust_cache and file_mtime(path) <= file_mtime(cache):
                    message("full cache", name)
                    fully_cached = True
                else:
                    message("partial cache", name)
            except KeyboardInterrupt:
                raise
            except Exception:
                message("corrupt cache", name)
                cached_album = None

        album = Album(rel_path)
        if fully_cached:
            for photo in cached_album.photos:
                album.add_photo(photo)

        to_process = []
        for entry in sorted(os.listdir(path)):
            if entry.startswith(".") or not fs_safe(entry):
                continue
            entry_path = os.path.join(path, entry)
            if os.path.isdir(entry_path):
                subalbum = self.walk(entry_path)
                if subalbum is not None:
                    album.add_album(subalbum)
                continue
            if fully_cached or not os.path.isfile(entry_path) or media_type_for(entry) is None:
                continue
            entry_rel = relative_path(entry_path, self.album_path)
            cached_photo = cached_album.photo_from_path(entry_rel) if cached_album else None
            if (
                cached_photo is not None
                and "dateTimeFile" in cached_photo.attributes
                and file_mtime(entry_path) <= cached_photo.attributes["dateTimeFile"]
                and self._caches_exist(cached_photo)
            ):
                next_level()
                message("cache hit", entry)
                back_level()
                album.add_photo(cached_photo)
            else:
                to_process.append((entry_path, entry_rel))

        if to_process:
            next_level()
            futures = [
                (entry_rel, self.pool.submit(process_media, entry_path, entry_rel, self.cache_path, self.options))
                for entry_path, entry_rel in to_process
            ]
            for entry_rel, future in futures:
                attributes = future.result()
                if attributes is None:
                    message("unreadable", os.path.basename(entry_rel))
                else:
                    album.add_photo(Photo(entry_rel, attributes))
            back_level()

        self.all_photos.extend(album.photos)
        if album.empty:
            message("empty", name)
            return None
        message("caching", name)
        album.cache(self.cache_path)
        self.all_albums.append(album)
        return album

    def big_lists(self):
        self.all_photos.sort(key=lambda p: (p.date, p.name))
        message("caching", "all photos path list")
        with open(os.path.join(self.cache_path, "all_photos.json"), "w", encoding="utf-8") as fp:
            json.dump([photo.path for photo in self.all_photos], fp, cls=PhotoAlbumEncoder, ensure_ascii=False)

    def remove_stale(self):
        message("cleanup", "building stale list")
        keep = {"all_photos.json", "latest_photos.json", OPTIONS_FILE}
        keep.update(album.cache_path for album in self.all_albums)
        for photo in self.all_photos:
            keep.update(photo.caches(self.options))
        message("cleanup", "searching for stale cache entries")
        for entry in os.listdir(self.cache_path):
            if entry not in keep:
                message("cleanup", entry)
                full = os.path.join(self.cache_path, entry)
                if os.path.isfile(full) or os.path.islink(full):
                    os.unlink(full)
