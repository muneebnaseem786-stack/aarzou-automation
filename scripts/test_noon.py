"""Quick test — Noon API auth + orders + inventory."""
import json, time, requests
import jwt

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
    "channel_identifier": "aarzoufzcllc@p242545.idp.noon.partners",
    "project_code": "PRJ242545",
}

BASE = "https://api.noon.partners"

now = int(time.time())

# Try with kid header (API gateway uses this to look up the public key)
token_with_kid = jwt.encode(
    {"iss": CREDS["key_id"], "sub": CREDS["channel_identifier"], "iat": now, "exp": now + 3600},
    CREDS["private_key"],
    algorithm="RS256",
    headers={"kid": CREDS["key_id"]},
)
print(f"JWT with kid generated OK (len={len(token_with_kid)})")

# Also try channel_identifier as iss
token_alt = jwt.encode(
    {"iss": CREDS["channel_identifier"], "sub": CREDS["key_id"], "iat": now, "exp": now + 3600},
    CREDS["private_key"],
    algorithm="RS256",
    headers={"kid": CREDS["key_id"]},
)

def test_endpoint(label, url, token, params=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.get(url, headers=headers, params=params or {}, timeout=30)
    print(f"\n--- {label} ---")
    print(f"Status: {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2)[:1000])
    except Exception:
        print(r.text[:600])

# Test variations
test_endpoint("v2/orders (kid JWT)", f"{BASE}/v2/orders", token_with_kid, {"limit": 5})
test_endpoint("v2/products (kid JWT)", f"{BASE}/v2/products", token_with_kid)
test_endpoint("v1/orders (kid JWT)", f"{BASE}/v1/orders", token_with_kid, {"limit": 5})
test_endpoint("v2/orders (alt JWT)", f"{BASE}/v2/orders", token_alt, {"limit": 5})
