"""Albums, photos and videos, plus the work of turning originals into
web sized images, video transcodes and metadata."""

import json
import math
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

from PIL import ExifTags, Image, ImageOps, TiffImagePlugin

from .cachepath import (
    DATE_FORMAT,
    file_mtime,
    image_cache,
    json_cache,
    message,
    video_cache,
)

try:  # optional: HEIC/HEIF support for iPhone photos
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

# Allow very large panoramas without Pillow's decompression bomb warning.
Image.MAX_IMAGE_PIXELS = 400_000_000

PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".jpe", ".png", ".gif", ".webp", ".tif", ".tiff",
    ".bmp", ".heic", ".heif", ".avif",
}
VIDEO_EXTENSIONS = {
    ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm", ".mts", ".m2ts",
    ".3gp", ".mpg", ".mpeg", ".wmv",
}

EXIF_IFD = 0x8769


def media_type_for(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in PHOTO_EXTENSIONS:
        return "photo"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def expected_caches(path, media_type, options):
    """All cache files a photo or video should have."""
    caches = [image_cache(path, size, True) for size in options["thumb_sizes"]]
    if media_type == "video":
        caches.append(video_cache(path))
    else:
        caches += [image_cache(path, size) for size in options["photo_sizes"]]
    return caches


class Album:
    def __init__(self, path):
        self.path = path
        self.photos = []
        self.albums = []

    def __str__(self):
        return self.path

    @property
    def cache_path(self):
        return json_cache(self.path)

    @property
    def date(self):
        dates = [p.date for p in self.photos] + [a.date for a in self.albums if not a.empty]
        return max(dates) if dates else datetime(1900, 1, 1)

    @property
    def empty(self):
        return not self.photos and all(album.empty for album in self.albums)

    def add_photo(self, photo):
        self.photos.append(photo)

    def add_album(self, album):
        self.albums.append(album)

    def _sort(self):
        self.photos.sort(key=lambda p: (p.date, p.name))
        self.albums.sort(key=lambda a: a.date)

    def cache(self, base_dir):
        self._sort()
        with open(os.path.join(base_dir, self.cache_path), "w", encoding="utf-8") as fp:
            json.dump(self, fp, cls=PhotoAlbumEncoder, ensure_ascii=False)

    @staticmethod
    def from_cache(path):
        with open(path, encoding="utf-8") as fp:
            dictionary = json.load(fp)
        album = Album(dictionary["path"])
        for photo in dictionary["photos"]:
            album.add_photo(Photo.from_dict(photo, album.path))
        return album

    def to_dict(self):
        self._sort()
        subalbums = []
        for sub in self.albums:
            if not sub.empty:
                name = sub.path[len(self.path):].lstrip("/") if self.path else sub.path
                subalbums.append({"path": name, "date": sub.date})
        return {"path": self.path, "date": self.date, "albums": subalbums, "photos": self.photos}

    def photo_from_path(self, path):
        for photo in self.photos:
            if photo.path == path:
                return photo
        return None


class Photo:
    def __init__(self, path, attributes):
        self.path = path
        self.attributes = attributes

    @property
    def name(self):
        return os.path.basename(self.path)

    def __str__(self):
        return self.name

    @property
    def media_type(self):
        return self.attributes.get("mediaType", "photo")

    def caches(self, options):
        return expected_caches(self.path, self.media_type, options)

    @property
    def date(self):
        for key in ("dateTimeVideo", "dateTimeOriginal", "dateTime", "dateTimeFile"):
            if key in self.attributes:
                return self.attributes[key]
        return datetime(1900, 1, 1)

    @staticmethod
    def from_dict(dictionary, album_path):
        dictionary = dict(dictionary)
        dictionary.pop("date", None)
        name = dictionary.pop("name")
        for key, value in dictionary.items():
            if key.startswith("dateTime") and isinstance(value, str):
                try:
                    dictionary[key] = datetime.strptime(value, DATE_FORMAT)
                except ValueError:
                    pass
        path = album_path + "/" + name if album_path else name
        return Photo(path, dictionary)

    def to_dict(self):
        photo = {"name": self.name, "date": self.date}
        photo.update(self.attributes)
        return photo


class PhotoAlbumEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime(DATE_FORMAT)
        if isinstance(obj, (Album, Photo)):
            return obj.to_dict()
        return super().default(obj)


# ---------------------------------------------------------------------------
# Processing. These functions run in worker processes, so they only take and
# return plain, picklable values.
# ---------------------------------------------------------------------------


def process_media(original_path, rel_path, cache_dir, options):
    """Create all cache files for one photo or video.

    Returns the attribute dictionary, or None if the file can't be used.
    """
    media_type = media_type_for(original_path)
    try:
        if media_type == "photo":
            return _process_photo(original_path, rel_path, cache_dir, options)
        if media_type == "video":
            return _process_video(original_path, rel_path, cache_dir, options)
    except KeyboardInterrupt:
        raise
    except Exception as e:  # one bad file must not stop the whole scan
        message("error", "%s: %s" % (os.path.basename(original_path), e))
    return None


# --- Photos -----------------------------------------------------------------


def _process_photo(original_path, rel_path, cache_dir, options):
    name = os.path.basename(original_path)
    attributes = {"dateTimeFile": file_mtime(original_path), "mediaType": "photo"}
    with Image.open(original_path) as image:
        attributes.update(_photo_metadata(image))
        icc_profile = image.info.get("icc_profile")
        image = ImageOps.exif_transpose(image)
    attributes["size"] = list(image.size)

    if image.mode == "CMYK":
        icc_profile = None  # the profile describes CMYK data, not our RGB output
    if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (34, 34, 34))  # page colour
        background.paste(image, mask=image.getchannel("A"))
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    save_options = {
        "quality": options["quality"],
        "optimize": True,
        "progressive": True,
    }
    if icc_profile:
        save_options["icc_profile"] = icc_profile

    # Large sizes first, each one resized from the previous one: much
    # faster than starting from the full size original every time.
    source = image
    for size in sorted(options["photo_sizes"], reverse=True):
        source = _resize_fit(source, size)
        _save(source, os.path.join(cache_dir, image_cache(rel_path, size)), name, size, False, save_options)

    square = _crop_square(image)
    for size in sorted(options["thumb_sizes"], reverse=True):
        square = _resize_fit(square, size)
        _save(square, os.path.join(cache_dir, image_cache(rel_path, size, True)), name, size, True, save_options)

    return attributes


def _resize_fit(image, size):
    width, height = image.size
    if max(width, height) <= size:
        return image
    scale = size / max(width, height)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS, reducing_gap=3.0)


def _crop_square(image):
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))


def _save(image, path, name, size, square, save_options):
    message("thumbing", "%s -> %dpx%s" % (name, size, ", square" if square else ""))
    tmp_path = path + ".tmp"
    try:
        image.save(tmp_path, "JPEG", **save_options)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _rational(value):
    """EXIF rationals become [numerator, denominator] for the web page."""
    if isinstance(value, TiffImagePlugin.IFDRational):
        if value.denominator == 0:
            return None
        return [value.numerator, value.denominator]
    if isinstance(value, tuple) and len(value) == 2 and all(isinstance(v, int) for v in value):
        return list(value) if value[1] else None
    if isinstance(value, (int, float)):
        return value
    return None


def _clean(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    if isinstance(value, str):
        value = value.partition("\x00")[0].strip()
        return value or None
    if isinstance(value, (tuple, list)) and len(value) >= 1:
        return _clean(value[0])
    if isinstance(value, TiffImagePlugin.IFDRational):
        return float(value)
    return value


def _parse_exif_date(value):
    value = _clean(value)
    if not isinstance(value, str):
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None


def parse_iso_date(value):
    """Parse an ISO 8601 date, returning naive local time."""
    if not isinstance(value, str):
        return None
    try:
        date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return date.replace(tzinfo=None)


def _photo_metadata(image):
    attributes = {}
    exif = {}
    try:
        raw = image.getexif()
        exif.update(raw)
        exif.update(raw.get_ifd(EXIF_IFD))
    except Exception:
        pass
    tags = {ExifTags.TAGS.get(tag, tag): value for tag, value in exif.items()}

    if not tags:
        # e.g. PNGs exported by some tools keep the date in text chunks
        for key in ("date:modify", "date:create", "Creation Time"):
            date = parse_iso_date(image.info.get(key))
            if date:
                attributes["dateTimeOriginal"] = date
                break
        return attributes

    orientation = _clean(tags.get("Orientation"))
    if isinstance(orientation, int) and 1 <= orientation <= len(ORIENTATION_LIST):
        attributes["orientation"] = ORIENTATION_LIST[orientation - 1]

    for attr, tag in (("make", "Make"), ("model", "Model"), ("lens", "LensModel"),
                      ("spectralSensitivity", "SpectralSensitivity")):
        value = _clean(tags.get(tag))
        if isinstance(value, str):
            attributes[attr] = value
    if "lens" not in attributes:
        value = _clean(tags.get("LensMake"))
        if isinstance(value, str):
            attributes["lens"] = value

    # FNumber is the f-stop; ApertureValue is an APEX value that has to be
    # converted (f = 2 ^ (Av / 2)).
    aperture = _rational(tags.get("FNumber"))
    if aperture is None:
        apex = _rational(tags.get("ApertureValue"))
        if apex is not None:
            value = apex[0] / apex[1] if isinstance(apex, list) else apex
            aperture = [round(math.pow(2, value / 2) * 10), 10]
    if aperture is not None:
        attributes["aperture"] = aperture

    for attr, tag in (("focalLength", "FocalLength"), ("exposureTime", "ExposureTime"),
                      ("exposureCompensation", "ExposureBiasValue")):
        value = _rational(tags.get(tag))
        if value is not None:
            attributes[attr] = value

    for tag in ("PhotographicSensitivity", "ISOSpeedRatings", "ISO"):
        value = _clean(tags.get(tag))
        if isinstance(value, int) and value > 0:
            attributes["iso"] = value
            break

    for attr, tag, table in (
        ("flash", "Flash", FLASH_DICTIONARY),
        ("lightSource", "LightSource", LIGHT_SOURCE_DICTIONARY),
        ("exposureProgram", "ExposureProgram", EXPOSURE_LIST),
        ("meteringMode", "MeteringMode", METERING_LIST),
        ("sensingMethod", "SensingMethod", SENSING_METHOD_LIST),
        ("sceneCaptureType", "SceneCaptureType", SCENE_CAPTURE_TYPE_LIST),
        ("subjectDistanceRange", "SubjectDistanceRange", SUBJECT_DISTANCE_RANGE_LIST),
    ):
        value = _clean(tags.get(tag))
        if isinstance(value, int):
            if isinstance(table, dict) and value in table:
                attributes[attr] = table[value]
            elif isinstance(table, list) and 0 <= value < len(table):
                attributes[attr] = table[value]

    for attr, tag in (("dateTimeOriginal", "DateTimeOriginal"), ("dateTime", "DateTime")):
        date = _parse_exif_date(tags.get(tag))
        if date:
            attributes[attr] = date

    return attributes


FLASH_DICTIONARY = {0x0: "No Flash", 0x1: "Fired", 0x5: "Fired, Return not detected", 0x7: "Fired, Return detected", 0x8: "On, Did not fire", 0x9: "On, Fired", 0xd: "On, Return not detected", 0xf: "On, Return detected", 0x10: "Off, Did not fire", 0x14: "Off, Did not fire, Return not detected", 0x18: "Auto, Did not fire", 0x19: "Auto, Fired", 0x1d: "Auto, Fired, Return not detected", 0x1f: "Auto, Fired, Return detected", 0x20: "No flash function", 0x30: "Off, No flash function", 0x41: "Fired, Red-eye reduction", 0x45: "Fired, Red-eye reduction, Return not detected", 0x47: "Fired, Red-eye reduction, Return detected", 0x49: "On, Red-eye reduction", 0x4d: "On, Red-eye reduction, Return not detected", 0x4f: "On, Red-eye reduction, Return detected", 0x50: "Off, Red-eye reduction", 0x58: "Auto, Did not fire, Red-eye reduction", 0x59: "Auto, Fired, Red-eye reduction", 0x5d: "Auto, Fired, Red-eye reduction, Return not detected", 0x5f: "Auto, Fired, Red-eye reduction, Return detected"}
LIGHT_SOURCE_DICTIONARY = {0: "Unknown", 1: "Daylight", 2: "Fluorescent", 3: "Tungsten (incandescent light)", 4: "Flash", 9: "Fine weather", 10: "Cloudy weather", 11: "Shade", 12: "Daylight fluorescent (D 5700 - 7100K)", 13: "Day white fluorescent (N 4600 - 5400K)", 14: "Cool white fluorescent (W 3900 - 4500K)", 15: "White fluorescent (WW 3200 - 3700K)", 17: "Standard light A", 18: "Standard light B", 19: "Standard light C", 20: "D55", 21: "D65", 22: "D75", 23: "D50", 24: "ISO studio tungsten"}
METERING_LIST = ["Unknown", "Average", "Center-weighted average", "Spot", "Multi-spot", "Multi-segment", "Partial"]
EXPOSURE_LIST = ["Not Defined", "Manual", "Program AE", "Aperture-priority AE", "Shutter speed priority AE", "Creative (Slow speed)", "Action (High speed)", "Portrait", "Landscape", "Bulb"]
ORIENTATION_LIST = ["Horizontal (normal)", "Mirror horizontal", "Rotate 180", "Mirror vertical", "Mirror horizontal and rotate 270 CW", "Rotate 90 CW", "Mirror horizontal and rotate 90 CW", "Rotate 270 CW"]
SENSING_METHOD_LIST = ["Not defined", "Not defined", "One-chip color area sensor", "Two-chip color area sensor", "Three-chip color area sensor", "Color sequential area sensor", "Not defined", "Trilinear sensor", "Color sequential linear sensor"]
SCENE_CAPTURE_TYPE_LIST = ["Standard", "Landscape", "Portrait", "Night scene"]
SUBJECT_DISTANCE_RANGE_LIST = ["Unknown", "Macro", "Close view", "Distant view"]


# --- Videos -----------------------------------------------------------------


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _probe(path):
    try:
        output = subprocess.run(
            ["ffprobe", "-v", "quiet", "-of", "json", "-show_format", "-show_streams", path],
            check=True, capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    info = json.loads(output)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video" and stream.get("disposition", {}).get("attached_pic") != 1:
            return info, stream
    return None


def _video_date(info):
    tags = info.get("format", {}).get("tags", {})
    # Apple's tag is in the local time of the camera; prefer it.
    date = parse_iso_date(tags.get("com.apple.quicktime.creationdate"))
    if date:
        return date
    value = tags.get("creation_time")
    if isinstance(value, str):
        try:
            date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if date.tzinfo is not None:
            date = date.astimezone().replace(tzinfo=None)
        if date.year > 1970:
            return date
    return None


def _process_video(original_path, rel_path, cache_dir, options):
    name = os.path.basename(original_path)
    if not ffmpeg_available():
        message("skipping", "%s (install ffmpeg for video support)" % name)
        return None
    probed = _probe(original_path)
    if probed is None:
        return None
    info, _stream = probed
    attributes = {"dateTimeFile": file_mtime(original_path), "mediaType": "video"}
    date = _video_date(info)
    if date:
        attributes["dateTimeVideo"] = date

    # Thumbnail: one frame, ffmpeg applies the rotation from the metadata.
    fd, frame_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        for seek in ("1", "0"):
            result = subprocess.run(
                ["ffmpeg", "-v", "quiet", "-y", "-ss", seek, "-i", original_path,
                 "-frames:v", "1", "-an", frame_path],
                capture_output=True,
            )
            if result.returncode == 0 and os.path.getsize(frame_path) > 0:
                break
        else:
            message("no video frame", name)
            return None
        with Image.open(frame_path) as frame:
            square = _crop_square(frame.convert("RGB"))
        save_options = {"quality": options["quality"], "optimize": True, "progressive": True}
        for size in sorted(options["thumb_sizes"], reverse=True):
            square = _resize_fit(square, size)
            _save(square, os.path.join(cache_dir, image_cache(rel_path, size, True)), name, size, True, save_options)
    finally:
        try:
            os.unlink(frame_path)
        except OSError:
            pass

    # Transcode to H.264/AAC MP4 that every browser can play, with the
    # short side limited to options["video_size"] pixels.
    transcode_path = os.path.join(cache_dir, video_cache(rel_path))
    tmp_path = transcode_path + ".tmp.mp4"
    limit = int(options["video_size"])
    scale = (
        "scale=w='if(gt(iw,ih),-2,min(%d,iw))':h='if(gt(iw,ih),min(%d,ih),-2)'" % (limit, limit)
    )
    message("transcoding", "%s -> mp4, h264, %dp" % (name, limit))
    command = [
        "ffmpeg", "-v", "error", "-y", "-i", original_path,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", scale,
        "-c:v", "libx264", "-preset", "slow", "-crf", "21",
        "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-maxrate", "12M", "-bufsize", "24M",
        "-c:a", "aac", "-ac", "2", "-b:a", "160k",
        "-movflags", "+faststart",
        "-f", "mp4", tmp_path,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            message("transcode fail", "%s: %s" % (name, result.stderr.strip()[-300:]))
            return None
        os.replace(tmp_path, transcode_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    probed = _probe(transcode_path)
    if probed is None:
        return None
    info, stream = probed
    attributes["size"] = [int(stream["width"]), int(stream["height"])]
    duration = stream.get("duration") or info.get("format", {}).get("duration")
    if duration:
        attributes["duration"] = duration
    return attributes
