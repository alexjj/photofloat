# PhotoFloat
### A Web 2.0 Photo Gallery Done Right via Static JSON & Dynamic Javascript
#### by Jason A. Donenfeld (<Jason@zx2c4.com>), modified by Joachim Tingvold (<joachim@tingvold.com>)

![Screenshot](http://data.zx2c4.com/photo-float-small.jpg)

PhotoFloat is an open source web photo gallery aimed at sleekness and speed. It keeps with an old hat mentality, preferring to work over directory structures rather than esoteric photo database management software. Everything it generates is static, which means it's extremely fast.

[Check out a demo!](http://photos.jasondonenfeld.com/#santa_fe_and_telluride_8.19.10-8.27.10/western_202.jpg)

## How It Works

PhotoFloat consists of two segments – a Python script and a JavaScript application.

The Python script scans a directory tree of images, whereby each directory constitutes an album. It then populates a second folder, known as the cache folder with statically generated JSON files and thumbnails. The scanner extracts metadata from EXIF tags in JPEG photos. PhotoFloat is smart about file and directory modification time, so you are free to run the scanner script as many times as you want, and it will be very fast if there are few or zero changes since the last time you ran it.

The JavaScript application consists of a single `index.html` file with plain JavaScript and CSS files, and no build step. It fetches the statically generated JSON files and thumbnails on the fly from the `cache` folder to create a speedy interface. Features include:

* Animations to make the interface feel nice
* Separate album view and photo view
* Album metadata pre-fetching
* Photo pre-loading
* Recursive async randomized tree walking album thumbnail algorithm
* Smooth up and down scaling
* Mouse-wheel and keyboard support (arrow keys, Escape to go back to the album)
* Metadata display
* Consistant hash url format
* Linkable states via ajax urls
* Facebook meta tags for thumbnail and post type
* Link to original images (can be turned off)
* Optional server-side authentication support
* A thousand other tweaks here and there...

It is, essentially, the slickest and fastest, most minimal but still well-featured photo gallery app on the net.

Changes from 'stock' PhotoFloat:

* HTML5-ified somewhat (including video support)
* Thumb generation is now threaded to save some time
* Threaded transcoding of videos
* Images are preloaded to avoid having to wait
* All JavaScript libraries was updated (including broken jQuery Mousewheel)
* Add logic to check that thumbs/transcode actually exist (to make sure they are recreated if deleted)
* Use more sane values for video transcoding (i.e. H264 rather than WebM)
* Handle old and weird videos (we try several types of transcodes)
* Improved loading of videos when browsing galleries
* Lots of bugfixes
* Properly handle PNG images (thumbs and timestamps from EXIF)
* Better handling of timestamps in general

Changes in 2.0:

* Python 3 scanner, installable as a single `photofloat` command with a `photofloat.toml` settings file
* High resolution photos (up to 4K by default) and 2x thumbnails, picked to suit each visitor's screen
* Colour profiles are kept, so photos look right on wide-gamut screens
* Photos are processed in parallel, one per CPU core
* No front-end build step and no JavaScript libraries; the page is plain JavaScript using the system fonts
* Phone friendly: thumbnail grid that fills the screen, swipe between photos, centred photos, always-visible photo links on touch screens
* Built-in preview server (`photofloat serve`)
* HEIC support (optional), correct f-numbers, lens info, videos up to 1080p with modern rotation handling


## Quick start

You need **Python 3.10+** and, for videos, **ffmpeg** (`brew install ffmpeg`, `sudo apt install ffmpeg`, …).

    git clone https://github.com/alexjj/photofloat.git
    cd photofloat
    pip install .            # or: pipx install .   /   uv tool install .

Put your photos in `web/albums`, one folder per album (sub-folders become sub-albums; symlinks are fine). Then:

    photofloat scan          # build thumbnails, web-sized photos and album data
    photofloat serve         # preview at http://localhost:8000

That's it. To publish, upload the whole `web` folder to any static web host (nginx, Apache, Netlify, an S3 bucket, …). Run `photofloat scan` again whenever you add or change photos; it only processes what changed, and removes files for photos you deleted.

Without installing, `python3 -m photofloat scan` works from the repository folder too (you need Pillow: `pip install Pillow`). For iPhone HEIC photos, install with `pip install ".[heif]"`.

## Settings

Settings live in `photofloat.toml` in the folder you run `photofloat` from. Every setting is optional:

| Setting | Default | What it does |
| --- | --- | --- |
| `title` | `"Photos"` | Gallery title on the page and browser tab |
| `site` | `"web"` | The folder you upload to your web host |
| `albums` / `cache` | `web/albums` / `web/cache` | Where your photos are, and where generated files go. Albums can live anywhere, but must be served at `albums/` on the site for "download original" to work |
| `photo_sizes` | `[1280, 2048, 3840]` | Longest side, in pixels, of the photos in the viewer. The page picks the smallest size that is sharp on the visitor's screen (taking high-DPI/retina screens into account), and loads a bigger one if the window grows or goes fullscreen |
| `thumb_sizes` | `[150, 300]` | Square thumbnails; 300 is used on high-DPI screens |
| `quality` | `85` | JPEG quality |
| `video_size` | `1080` | Videos are converted to H.264 MP4 with the short side at most this many pixels |
| `download_originals` | `true` | Show the "download original" link |
| `jobs` | `0` | Photos processed in parallel; 0 = all CPU cores |

Each one can also be given on the command line, e.g. `photofloat scan --title "Our Trips" --photo-sizes 1600,2560,3840`; see `photofloat scan --help`. You can also point at folders directly: `photofloat scan ALBUM_PATH CACHE_PATH`.

If you change `photo_sizes` or `thumb_sizes`, the next scan creates the new sizes and deletes the old ones. Changing `quality` or `video_size` only affects new photos; delete the cache folder to regenerate everything.

## Customising the page

Edit `web/index.html` for a copyright notice or analytics snippet, and `web/css/photofloat.css` for the look. There is no build step: the page is plain HTML, CSS and JavaScript with no dependencies.

## What the scanner does

For every photo it reads the EXIF data (camera, lens, exposure, date taken, …), applies the EXIF rotation, keeps the colour profile, and writes square thumbnails and web-sized JPEGs to the cache folder. Videos get a thumbnail and an MP4 copy every browser can play. Each album gets a small JSON file the page loads on demand. Photos are sorted by the date they were taken.

## Optional: Server-side Authentication

The JavaScript application uses a very simple API to determine if a photo can be viewed or not. If a JSON file returns error `403`, the album is hidden from view. To authenticate, a username and a password are sent to `/auth`. If unsuccessful, `403` is returned. If successful, `200` is returned, and the previously denied json files may now be requested. If an unauthorized album is directly requested in a URL when the page loads, an authentication box is shown.

PhotoFloat ships with an optional server side component called FloatApp to facilitate this, in `photofloat/floatapp`. It is a small Flask application:

    pip install ".[server]" gunicorn

Edit `photofloat/floatapp/app.cfg` with a username and password for both an admin user and a photo user, a secret key, and the album and cache paths (or set the `PHOTOFLOAT_APP_CONFIG` environment variable to a config file elsewhere). The admin user is allowed to call `/scan?username=…&password=…`, which runs the scanner.

List the protected albums or photos in `photofloat/floatapp/auth.txt` (or the file named by `PHOTOFLOAT_AUTH_LIST`), one path per line.

Run it with `gunicorn -b 127.0.0.1:5000 photofloat.floatapp:app` and send `/albums/`, `/cache/`, `/scan`, `/auth` and `/photos` to it from nginx. FloatApp uses `X-Accel-Redirect` so nginx serves the files itself:

    server {
            listen 80;
            server_name photos.example.com;
            root /var/www/photofloat/web;
            index index.html;

            location ~ ^/(albums|cache)/ { proxy_pass http://127.0.0.1:5000; }
            location ~ ^/(scan|auth|photos)$ { proxy_pass http://127.0.0.1:5000; proxy_buffering off; }

            location /internal-cache/ {
                    internal;
                    alias /var/www/photofloat/web/cache/;
            }
            location /internal-albums/ {
                    internal;
                    alias /var/www/photofloat/web/albums/;
            }
    }

The `internal-*` paths must match `ALBUM_ACCEL` and `CACHE_ACCEL` in `app.cfg`.

## Mailing List & Suggestions

If you have any suggestions, feel free to contact the PhotoFloat community via [our mailing list](http://lists.zx2c4.com/mailman/listinfo/photofloat). We're open to adding all sorts of features and working on integration points with other pieces of software.

## License

Copyright (C) 2010 - 2014 Jason A. Donenfeld. All Rights Reserved.

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
