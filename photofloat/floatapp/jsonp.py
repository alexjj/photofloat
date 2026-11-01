import re
from functools import wraps

from flask import current_app, request

jsonp_validator = re.compile(r"^[a-zA-Z0-9_\-.]{1,128}$")


def jsonp(f):
    """Wraps JSONified output for JSONP"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        callback = request.args.get("callback", False)
        if callback and jsonp_validator.match(callback):
            content = callback + "(" + f(*args, **kwargs).get_data(as_text=True) + ")"
            return current_app.response_class(content, mimetype="application/javascript")
        return f(*args, **kwargs)

    return decorated_function
