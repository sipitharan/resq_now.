from urllib.parse import quote

import requests
from flask import current_app


def is_configured():
    return bool(current_app.config["SUPABASE_URL"] and current_app.config["SUPABASE_SERVICE_ROLE_KEY"])


def _object_url(name):
    bucket = quote(current_app.config["SUPABASE_STORAGE_BUCKET"], safe="")
    object_name = quote(name, safe="")
    return f"{current_app.config['SUPABASE_URL']}/storage/v1/object/{bucket}/{object_name}"


def _headers(content_type=None):
    key = current_app.config["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def upload_private_object(name, path, content_type):
    response = requests.post(
        _object_url(name),
        headers={**_headers(content_type), "x-upsert": "false"},
        data=path.read_bytes(),
        timeout=30,
    )
    response.raise_for_status()


def download_private_object(name):
    response = requests.get(_object_url(name), headers=_headers(), timeout=30)
    response.raise_for_status()
    return response.content, response.headers.get("Content-Type", "application/octet-stream")
