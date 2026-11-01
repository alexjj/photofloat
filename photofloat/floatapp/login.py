import hmac
from functools import wraps

from flask import abort, request
from flask_login import UserMixin, current_user

from . import app, login_manager


class User(UserMixin):
    def __init__(self, id, admin=False):
        self.admin = admin
        self.id = id


photo_user = User("user")
admin_user = User("admin", True)


@login_manager.user_loader
def load_user(id):
    if id == "user":
        return photo_user
    if id == "admin":
        return admin_user
    return None


@login_manager.unauthorized_handler
def unauthorized():
    return abort(403)


def _matches(query, user_key, password_key):
    username = query.get("username") or ""
    password = query.get("password") or ""
    return hmac.compare_digest(username, app.config[user_key]) and hmac.compare_digest(
        password, app.config[password_key]
    )


def query_is_photo_user(query):
    return _matches(query, "PHOTO_USERNAME", "PHOTO_PASSWORD")


def query_is_admin_user(query):
    return _matches(query, "ADMIN_USERNAME", "ADMIN_PASSWORD")


def is_authenticated():
    return query_is_admin_user(request.args) or query_is_photo_user(request.args) or current_user.is_authenticated


def login_required(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if is_authenticated():
            return fn(*args, **kwargs)
        return login_manager.unauthorized()

    return decorated_view


def admin_required(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if query_is_admin_user(request.args) or (current_user.is_authenticated and current_user.admin):
            return fn(*args, **kwargs)
        return login_manager.unauthorized()

    return decorated_view
