"""Optional server side component for password protected albums.

Run with any WSGI server, e.g.:  gunicorn photofloat.floatapp:app
Needs:  pip install "photofloat[server]"
"""

import os

from flask import Flask
from flask_login import LoginManager

here = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config.from_pyfile(os.environ.get("PHOTOFLOAT_APP_CONFIG", os.path.join(here, "app.cfg")))
login_manager = LoginManager()
login_manager.init_app(app)

from . import login, endpoints  # noqa: E402,F401  (registers routes)
