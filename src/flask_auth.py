"""
Optional auth for local Flask tools. When ADMIN_SECRET env var is set,
all /api/* and /images/* routes require X-Admin-Token or Authorization: Bearer header.

Usage: call register_admin_auth(app) after creating your Flask app.
"""

import os

from flask import jsonify, request


def _get_admin_secret() -> str | None:
    return os.environ.get("ADMIN_SECRET") or os.environ.get("FLASK_ADMIN_SECRET")


def _is_protected_path() -> bool:
    path = request.path
    return path.startswith("/api/") or path.startswith("/images/")


def _get_provided_token() -> str | None:
    # Check X-Admin-Token header first
    token = request.headers.get("X-Admin-Token")
    if token:
        return token
    # Check Authorization: Bearer
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def register_admin_auth(app):
    """
    Register optional admin auth. When ADMIN_SECRET is set, protect /api/* and /images/*.
    """
    secret = _get_admin_secret()
    if not secret:
        return

    @app.before_request
    def require_admin_token():
        if not _is_protected_path():
            return None
        provided = _get_provided_token()
        if not provided or provided != secret:
            return jsonify({"error": "Unauthorized. Set X-Admin-Token or Authorization: Bearer."}), 401
        return None
