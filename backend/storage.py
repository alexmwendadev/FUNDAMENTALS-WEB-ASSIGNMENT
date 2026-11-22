"""Saves uploaded images. Local disk by default; Cloudinary when CLOUDINARY_URL
is set (needed on hosts whose disk is wiped on every restart)."""
# standard library: hashlib for Cloudinary's signature, re for patterns, time for timestamps,
# uuid for unguessable file names, Path for file paths, urlparse/unquote to read CLOUDINARY_URL
import hashlib
import logging
import re
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

# my settings (upload folder, Cloudinary link)
import config

# shared logger
log = logging.getLogger("shamba")


# raised when an image can't be saved; main.py shows the user a friendly message
class StorageError(Exception):
    pass


# ---------- local disk ----------
# turns a stored '/uploads/...' address into a real file path on disk, or None if it isn't one of mine
def _local_path(url):
    # only addresses that start with /uploads/ are local files
    if not url or not url.startswith("/uploads/"):
        return None
    # the absolute path of the uploads folder
    base = Path(config.UPLOAD_DIR).resolve()
    # the full path of the file, with any '..' tricks resolved
    path = (base / url[len("/uploads/"):]).resolve()
    # refuse anything that points outside the uploads folder (path traversal protection)
    return path if base in path.parents else None  # never leave the uploads folder


# writes the image into uploads/<folder>/ and returns its address
def _save_local(data, ext, folder):
    # e.g. uploads/products or uploads/avatars
    target_dir = Path(config.UPLOAD_DIR) / folder
    # create the folder if it doesn't exist yet
    target_dir.mkdir(parents=True, exist_ok=True)
    # random name so files never clash and can't be guessed
    name = f"{uuid.uuid4().hex}{ext}"
    # write the image bytes to disk
    (target_dir / name).write_bytes(data)
    # this address is what gets stored in the database
    return f"/uploads/{folder}/{name}"


# ---------- Cloudinary ----------
# reads api key, secret and cloud name out of CLOUDINARY_URL (cloudinary://key:secret@cloud)
def _cloudinary():
    # split the link into its parts
    parsed = urlparse(config.CLOUDINARY_URL)
    # cloud name, api key, api secret (unquote undoes %-encoding)
    return parsed.hostname, unquote(parsed.username or ""), unquote(parsed.password or "")


# Cloudinary wants every request signed: sha1 of the sorted parameters plus the secret
def _sign(params, secret):
    # key=value pairs in alphabetical order, joined with &, then the secret on the end
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params)) + secret
    # the signature as hex text
    return hashlib.sha1(to_sign.encode()).hexdigest()


# uploads the image to Cloudinary and returns its https link
def _save_cloudinary(data, ext, folder):
    # HTTP library, imported only when Cloudinary is actually used
    import requests
    # credentials
    cloud, key, secret = _cloudinary()
    # files go into a 'shamba/<folder>' folder; the timestamp is part of the signature
    params = {"folder": f"shamba/{folder}", "timestamp": str(int(time.time()))}
    # any network or Cloudinary failure becomes a StorageError
    try:
        # send the upload
        resp = requests.post(
            # Cloudinary's upload address for my cloud
            f"https://api.cloudinary.com/v1_1/{cloud}/image/upload",
            # the signed form fields
            data={**params, "api_key": key, "signature": _sign(params, secret)},
            # the image itself
            files={"file": (f"upload{ext}", data)},
            # give up after 30 seconds instead of hanging
            timeout=30,
        )
        # turn an HTTP error reply into an exception
        resp.raise_for_status()
        # the https link of the stored image
        return resp.json()["secure_url"]
    # upload failed
    except Exception as exc:
        # pass it up in my own error type
        raise StorageError(f"Cloudinary upload failed: {exc}") from exc


# works out Cloudinary's public id from an image link (needed to delete it)
def _cloudinary_public_id(url):
    # the part after /upload/ (and an optional v123456/ version), minus the file extension
    match = re.search(r"/upload/(?:v\d+/)?(.+)\.[A-Za-z0-9]+$", url)
    # None if the link didn't look like a Cloudinary link
    return match.group(1) if match else None


# asks Cloudinary to delete an image
def _delete_cloudinary(url):
    # HTTP library
    import requests
    # which image
    public_id = _cloudinary_public_id(url)
    # couldn't tell: do nothing
    if not public_id:
        return
    # credentials
    cloud, key, secret = _cloudinary()
    # signed delete request
    params = {"public_id": public_id, "timestamp": str(int(time.time()))}
    # send it (the reply is ignored: a failed delete only leaves an unused file)
    requests.post(
        f"https://api.cloudinary.com/v1_1/{cloud}/image/destroy",
        data={**params, "api_key": key, "signature": _sign(params, secret)},
        timeout=15,
    )


# ---------- public API ----------
# the function main.py calls: stores the bytes and returns what to keep in the database.
# Cloudinary when it is configured, otherwise local disk
def save_image(data, ext, folder):
    """Store the bytes and return the URL/path to keep in the database."""
    # Cloudinary is set up: use it
    if config.CLOUDINARY_URL:
        # returns a full https link
        return _save_cloudinary(data, ext, folder)
    # local disk otherwise
    try:
        # returns an /uploads/... address
        return _save_local(data, ext, folder)
    # disk full, no permission, etc.
    except OSError as exc:
        # report it in my own error type
        raise StorageError(f"Could not save the image: {exc}") from exc


# removes an image file; never raises, because a leftover file must not break the request that asked for the cleanup
def delete_image(url):
    """Best effort: a leftover file must never break the request that triggered the cleanup."""
    # nothing stored: nothing to delete
    if not url:
        return
    # any failure below is only logged
    try:
        # a full link means it lives on Cloudinary
        if url.startswith("http"):
            # only delete if it really is Cloudinary and it's configured
            if "res.cloudinary.com" in url and config.CLOUDINARY_URL:
                # ask Cloudinary to remove it
                _delete_cloudinary(url)
            # a link that isn't Cloudinary is left alone
            return
        # otherwise it's a local file: find it on disk
        path = _local_path(url)
        # only delete if it exists and is inside the uploads folder
        if path and path.is_file():
            # delete the file
            path.unlink()
    # never let a cleanup problem break the request
    except Exception:
        # just write the problem to the log
        log.exception("Could not delete image %s", url)
