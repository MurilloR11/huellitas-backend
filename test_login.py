"""Script temporal para probar el login y el endpoint de fundaciones pendientes."""
import os
import urllib.request
import urllib.error
import json
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
ANON_KEY     = os.environ["SUPABASE_ANON_KEY"]
EMAIL        = input("Email del admin: ").strip()
PASSWORD     = input("Password del admin: ").strip()

# 1. Login
print("\n--- Login ---")
body = json.dumps({"email": EMAIL, "password": PASSWORD}).encode()
req = urllib.request.Request(
    f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
    data=body,
    headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req) as r:
        login_data = json.loads(r.read())
except urllib.error.HTTPError as e:
    print("Error HTTP", e.code, e.reason)
    print("Detalle:", e.read().decode() or "(vacío)")
    raise SystemExit(1)

token = login_data["access_token"]
print("Login OK. Token:", token[:50], "...")

# 2. GET /foundations/pending
print("\n--- GET /foundations/pending ---")
req2 = urllib.request.Request(
    "http://localhost:5000/foundations/pending",
    headers={"Authorization": f"Bearer {token}"},
)
try:
    with urllib.request.urlopen(req2) as r:
        result = json.loads(r.read())
    print("Respuesta:", json.dumps(result, indent=2, ensure_ascii=False))
except urllib.error.HTTPError as e:
    print("Error HTTP", e.code, e.reason)
    print("Detalle:", e.read().decode() or "(vacío)")
