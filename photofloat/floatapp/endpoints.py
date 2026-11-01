import os
import sys
from mimetypes import guess_type
from random import shuffle

from flask import Response, abort, json, jsonify, request
from flask_login import current_user, login_user

from ..cachepath import cache_name
from . import app, here
from .jsonp import jsonp
from .login import (
    admin_required,
    admin_user,
    is_authenticated,
    photo_user,
    query_is_admin_user,
    query_is_photo_user,
)
from .process import send_process


@app.route("/scan")
@admin_required
def scan_photos():
    response = send_process(
        [sys.executable, "-u", "-m", "photofloat", "scan",
         "--albums", os.path.abspath(app.config["ALBUM_PATH"]),
         "--cache", os.path.abspath(app.config["CACHE_PATH"])],
        os.path.join(here, "scanner.pid"),
    )
    response.headers.add("X-Accel-Buffering", "no")
    response.cache_control.no_cache = True
    return response


@app.route("/auth", methods=["GET", "POST"])
def login():
    success = False
    if current_user.is_authenticated:
        success = True
    elif query_is_photo_user(request.form) or query_is_photo_user(request.args):
        success = login_user(photo_user, remember=True)
    elif query_is_admin_user(request.form) or query_is_admin_user(request.args):
        success = login_user(admin_user, remember=True)
    if not success:
        abort(403)
    return ""


auth_list = []


def read_auth_list():
    global auth_list
    paths = []
    auth_file = os.environ.get("PHOTOFLOAT_AUTH_LIST", os.path.join(here, "auth.txt"))
    with open(auth_file, encoding="utf-8") as f:
        for path in f:
            path = path.strip()
            if path:
                paths.append(path)
                paths.append(cache_name(path))
    auth_list = paths


# TODO: Make this run via inotify
read_auth_list()


def check_permissions(path):
    if not is_authenticated():
        for auth_path in auth_list:
            if path.startswith(auth_path) or path.startswith("root-" + auth_path):
                abort(403)


@app.route("/albums/<path:path>")
def albums(path):
    check_permissions(path)
    return accel_redirect(app.config["ALBUM_ACCEL"], app.config["ALBUM_PATH"], path)


@app.route("/cache/<path:path>")
def cache(path):
    check_permissions(path)
    return accel_redirect(app.config["CACHE_ACCEL"], app.config["CACHE_PATH"], path)


def accel_redirect(internal, real, relative_name):
    real_path = os.path.join(real, relative_name)
    internal_path = os.path.join(internal, relative_name)
    if not os.path.isfile(real_path):
        abort(404)
    mimetype = guess_type(real_path)[0]
    response = Response(mimetype=mimetype)
    response.headers.add("X-Accel-Redirect", internal_path)
    response.cache_control.public = True
    if mimetype == "application/json":
        response.cache_control.max_age = 3600
    else:
        response.cache_control.max_age = 29030400
    return response


@app.route("/photos")
@jsonp
def photos():
    with open(os.path.join(app.config["CACHE_PATH"], "all_photos.json"), encoding="utf-8") as f:
        photos = json.load(f)
    if not is_authenticated():
        def allowed(photo):
            return not any(photo.startswith(auth_path) for auth_path in auth_list)

        photos = [photo for photo in photos if allowed(photo)]
    count = int(request.args.get("count", len(photos)))
    if request.args.get("random") == "true":
        shuffle(photos)
    else:
        photos.reverse()
    response = jsonify(photos=photos[0:count])
    response.cache_control.no_cache = True
    return response
