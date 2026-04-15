"""Backward-compatible web app wrapper."""

from autofiller.web_app import DEFAULT_FLASK_PORT, app


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=DEFAULT_FLASK_PORT, debug=False)
