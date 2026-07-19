"""
Noon Partner API client.

Auth is a two-step handshake, documented from an earlier debugging session:
  1. Sign a JWT with the API key id + secret
  2. POST it to /identity/public/v1/api/login - the response sets session cookies
     which authenticate every subsequent call. There is NO bearer token.

Data comes out through an asynchronous export system: create an export job,
poll for status, download the resulting CSV.

Required in .env:
    NOON_KEY_ID
    NOON_SECRET
"""

import io
import os
import pathlib
import time
import uuid
from datetime import datetime, timezone

BASE = "https://noon-api-gateway.noon.partners"

EXPORTS = {
    "sales": "noon_catalog_reports_productviewsandsalesdata",
    "transactions": "noon_financeweb_transactionviewreportonitemlevel",
    "catalog": "noon_catalog_catalogexport",
}


def _from_json_file():
    """
    Preferred source: the credentials JSON Noon issues on key creation.
    Contains key_id, private_key (PEM), channel_identifier, project_code, type.

    Path comes from NOON_CREDENTIALS_FILE, else noon_credentials.json at the
    repo root. Returns (key_id, pem, meta) or (None, None, {}).
    """
    import json
    name = os.environ.get("NOON_CREDENTIALS_FILE", "noon_credentials.json").strip()
    p = pathlib.Path(name)
    if not p.is_absolute():
        p = pathlib.Path(__file__).resolve().parent.parent / p
    if not p.exists():
        return None, None, {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None, None, {}
    key_id = d.get("key_id") or d.get("keyId")
    pem = d.get("private_key") or d.get("privateKey")
    meta = {k: d.get(k) for k in ("channel_identifier", "project_code", "type")}
    return key_id, pem, meta


def _secret_material():
    """
    Returns (secret_text, algorithm).

    Noon issues an RSA private key, not a shared HMAC secret, so the JWT is
    signed with RS256. A PEM key cannot survive a single-line .env value, so the
    preferred route is NOON_SECRET_FILE pointing at the .pem file exactly as
    Noon supplied it. NOON_SECRET is still honoured for a genuine HMAC secret.
    """
    path = os.environ.get("NOON_SECRET_FILE", "").strip()
    if path:
        p = pathlib.Path(path)
        if not p.is_absolute():
            p = pathlib.Path(__file__).resolve().parent.parent / p
        if not p.exists():
            raise RuntimeError(f"NOON_SECRET_FILE points at a missing file: {p}")
        return p.read_text(encoding="utf-8"), "RS256"

    raw = os.environ.get("NOON_SECRET", "")
    if not raw:
        return "", None

    # Restore escaped newlines, then repair a PEM whose header was lost in paste.
    text = raw.replace("\\n", "\n").strip()
    looks_like_key = text.lstrip("n").startswith("MII") or "PRIVATE KEY" in text
    if looks_like_key:
        if "BEGIN" not in text:
            body = "".join(text.lstrip("n").split())
            wrapped = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
            text = ("-----BEGIN PRIVATE KEY-----\n" + wrapped +
                    "\n-----END PRIVATE KEY-----\n")
        return text, "RS256"
    return text, "HS256"


def credentials():
    key_id = os.environ.get("NOON_KEY_ID", "").strip()
    try:
        secret, _alg = _secret_material()
    except RuntimeError:
        secret = ""
    return key_id, secret


def is_live():
    kid, pem, _ = _from_json_file()
    if kid and pem:
        return True
    key_id, secret = credentials()
    return bool(key_id and secret)


def _make_jwt(key_id, secret_text, algorithm):
    """Noon expects sub / iat / jti only. Adding iss or exp caused 418s."""
    import jwt  # PyJWT
    payload = {
        "sub": key_id,
        "iat": int(time.time()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, secret_text, algorithm=algorithm)


def session():
    """
    Returns an authenticated requests.Session, or raises RuntimeError with a
    readable message.
    """
    import requests

    key_id, pem, meta = _from_json_file()
    if key_id and pem:
        secret, algorithm = pem, "RS256"
    else:
        key_id = os.environ.get("NOON_KEY_ID", "").strip()
        secret, algorithm = _secret_material()
    if not (key_id and secret):
        raise RuntimeError(
            "Missing Noon credentials. Set NOON_KEY_ID and NOON_SECRET_FILE in .env."
        )

    token = _make_jwt(key_id, secret, algorithm)
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "aarzou-cli/1.0",
    })
    r = s.post(f"{BASE}/identity/public/v1/api/login",
               json={"token": token}, timeout=30)
    if r.status_code != 200:
        body = (r.text or "")[:200]
        raise RuntimeError(f"Noon login failed: HTTP {r.status_code} - {body}")
    if not s.cookies:
        raise RuntimeError("Noon login returned 200 but set no session cookies.")
    return s


def inventory(s, partner_sku):
    """Net sellable stock for one partner SKU in the AE marketplace."""
    r = s.get(f"{BASE}/offer/v1/product/{partner_sku}", timeout=30)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return None, "unparseable response"

    rows = data if isinstance(data, list) else (data.get("data") or data.get("results") or [])
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows:
        if str(row.get("country_code", "")).lower() == "ae":
            for key in ("active_net_stock", "net_stock", "stock"):
                if key in row:
                    return row.get(key), None
    return None, "no AE row in response"


def create_export(s, category, date_from=None, date_to=None):
    """Start an export job. Returns (job_id, error)."""
    body = {"export_category": category}
    if date_from:
        body["date_from"] = date_from
    if date_to:
        body["date_to"] = date_to
    r = s.post(f"{BASE}/impex/v1/export/create", json=body, timeout=45)
    if r.status_code not in (200, 201, 202):
        return None, f"HTTP {r.status_code} - {(r.text or '')[:180]}"
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return None, "unparseable create response"
    for key in ("id", "export_id", "job_id", "reference"):
        if data.get(key):
            return data[key], None
    inner = data.get("data") or {}
    for key in ("id", "export_id", "job_id", "reference"):
        if inner.get(key):
            return inner[key], None
    return None, f"no job id in response: {str(data)[:180]}"


def poll_export(s, job_id, attempts=20, delay=6):
    """Poll until the export is ready. Returns (download_url, error)."""
    for _ in range(attempts):
        r = s.post(f"{BASE}/impex/v1/export/status", json={"id": job_id}, timeout=30)
        if r.status_code != 200:
            return None, f"status HTTP {r.status_code}"
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            return None, "unparseable status response"
        node = data.get("data") or data
        state = str(node.get("status") or node.get("state") or "").lower()
        url = node.get("url") or node.get("download_url") or node.get("file_url")
        if url:
            return url, None
        if state in ("failed", "error"):
            return None, f"export failed: {str(node)[:180]}"
        time.sleep(delay)
    return None, "timed out waiting for export"


def fetch_export(s, category, date_from=None, date_to=None):
    """Full cycle: create, poll, download. Returns (list_of_dicts, error)."""
    import csv
    job, err = create_export(s, category, date_from, date_to)
    if err:
        return None, err
    url, err = poll_export(s, job)
    if err:
        return None, err
    r = s.get(url, timeout=90)
    if r.status_code != 200:
        return None, f"download HTTP {r.status_code}"
    text = r.content.decode("utf-8-sig", errors="ignore")
    return list(csv.DictReader(io.StringIO(text))), None


def probe_exports(s, candidates):
    """
    Try creating each candidate export category to discover which exist.
    Used to find out whether Noon exposes advertising data at all.
    Returns list of (category, ok, detail).
    """
    out = []
    for cat in candidates:
        job, err = create_export(s, cat)
        if err:
            out.append((cat, False, err[:90]))
        else:
            out.append((cat, True, f"job {job}"))
        time.sleep(1.5)
    return out
