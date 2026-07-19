"""Test Noon API endpoints after successful login."""
import json, time, uuid, jwt, requests

CREDS = {
    "key_id": "noon-partners-key-id-93a0d12a59dd48ecb2aca3b6131bb9c7",
    "private_key": (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDhxzfo3xcJXM1g\n"
        "dQTXqSIsj3HPq0/URUGn2wVwrvcHAR05CLr++pijKLFcXdZcvaNrhscuZ2el5frw\n"
        "Ck+iO2iA949XD3YylyYybBXkQ8pl8BqawKwBXFtQNXDVgQ7+U3IOepoTgIzUI0Bl\n"
        "9ScqdBZCwBGQ4G4WhvPDlIAGx2JRMs0aK87cmmbVgYSpv3kzckQef/zdbfGEhhWl\n"
        "Djn7p3AmguifYjkeOzsFM1q/yhU39TNGiN//ejUouL6j8CJN1YrINCtTER7ms6gl\n"
        "wZX8ElA7Uz2bowcpX0tL2Jy2Wr5f5yWHBY1FRhzn0N/tbAepeonsZufq0tSKEFJV\n"
        "Q2ypdDwpAgMBAAECggEABmnwJOmngCDWhcG1QkIgAieOCmH5udRA1fmjGS0jP9vw\n"
        "flUI6OLqEKKAjVjuFMLfYFfbEy6lU2Fp5EVKt1dcM+O0evrptuyzzVVkNtCVMJmm\n"
        "S9Si3kQHJQtrmekZabCpqg8iDuFFPuaEdxEEjJBxLHLD3Pt/LR0m0hzHGUozOQ68\n"
        "dWhpsenaD7IcRSYAjg2JZNBskH70g9+oz3FOiKrnpUX5B+fc0eywGF4M5IgAoJAW\n"
        "0IjBGAjK6MZC2l5Qku/JyF6bLdbiHbqcsCgCn5Yq0mbzvRXOULGiFVGRWoFgigbR\n"
        "Tm5uiY5ZabQleZgvj99jyq6rz1ydTici1ubK9NkF4QKBgQD/F3CGUFkiOjSWz685\n"
        "z0kotnrdK8fVGoQlkJW/K/6JXcjTlgYWwzox9SqFZC14kGcQ4jRYyJYoe3RToo4B\n"
        "TY+6wZhwZy2asVhmXKWrUkxY1YMDdB3tzXEWfvKP9WYapPAh0D7s7NOe8d0VLp53\n"
        "qyMix+qWZyd+AHCZK6uFnef9uQKBgQDilQ36gNXqFmDWcLtGoxdF6nf1C0PctDx9\n"
        "WjQ2Mx5kD6D65JeKKquBKmpbhGV8KPO7qKBYN32mgFkytrHsk7s/AUuXqKyxQqDy\n"
        "9VLy7z38i2rvcxtwrMGVBrLf0Fvdh7H5vrfq6MY8o3m7T8epoVNtUgFAoY15+iU9\n"
        "4lAtxanp8QKBgACXdVNabFp/+A9BfA6ORIUrpy1MJLKB1TyhETfYSkbXSNf0yR7U\n"
        "ZRYok2irys80xohrfeOW04JUhviKr/mgzGyKdmgMVTa+oo3aOSgkkLjEBgHECy26\n"
        "BEEhGj7rOsllCImLihnSkssTlIewC/4LD5HNFOY0ZwsLxTcVutgcfaVBAoGBAMdV\n"
        "yo5vecIPHfKKCrgCEx93P0FdP76S8gR1rylfn4T4Gu+e25K6J1fjMN6Cg6XPgV2+\n"
        "5BG3/9rTX6W2BKHU9g5f3Vj3E7Z+n4ofOXJv92COZu1xntppoYSx9/vfGnKyRmko\n"
        "2DTZxEzkpNudPFKHkxXB50gs2IJPBySCTXd3RhyBAoGBAPrfmKX4rr00KXDfHDtp\n"
        "pbAKqQGO12Tx214tfRL19wW8AVK9F96K3TlpOjNrdYW0HrvEaPWVQAgj9UBmLlMK\n"
        "Z+WQm8S/PW1QJ8BtNrtrR0VpN8lbDKcxT3Pep6qoQtHNk1eEUT/LNDp9yy8QPWgO\n"
        "tIq2lz0zaB8kSu2w1JrQNgkk\n"
        "-----END PRIVATE KEY-----\n"
    ),
    "project_code": "PRJ242545",
}

BASE = "https://noon-api-gateway.noon.partners"
USER_AGENT = "AARZOU-Dashboard/1.0"

def get_session():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    token = jwt.encode(
        {"sub": CREDS["key_id"], "iat": int(time.time()), "jti": str(uuid.uuid4())},
        CREDS["private_key"], algorithm="RS256",
    )
    r = session.post(f"{BASE}/identity/public/v1/api/login",
                     json={"token": token, "default_project_code": CREDS["project_code"]},
                     timeout=30)
    assert r.status_code == 200, f"Login failed: {r.text}"
    print("Logged in OK")
    return session

session = get_session()

def probe(label, url, params=None):
    r = session.get(url, params=params or {}, timeout=30)
    print(f"\n[{r.status_code}] {label}")
    try:
        print(json.dumps(r.json(), indent=2)[:800])
    except Exception:
        print(r.text[:400])

# Try common endpoint patterns from the API categories seen in docs
endpoints = [
    ("orders v1",          f"{BASE}/order/v1/orders"),
    ("orders public v1",   f"{BASE}/order/public/v1/orders"),
    ("fbpi orders",        f"{BASE}/fbpi/v1/orders"),
    ("fbpo orders",        f"{BASE}/fbpo/v1/orders"),
    ("stock v1",           f"{BASE}/stock/v1/stock"),
    ("catalog v1",         f"{BASE}/catalog/v1/products"),
    ("offer v1",           f"{BASE}/offer/v1/offers"),
    ("reports v1",         f"{BASE}/reports/v1/reports"),
]

for label, url in endpoints:
    probe(label, url)
