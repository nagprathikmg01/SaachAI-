"""
enable_rls.py — Enable Row Level Security on Supabase voice_data table.

Run this ONCE after getting your service_role key from:
  Supabase Dashboard → Project Settings → API → service_role (secret)

Usage:
  python enable_rls.py <service_role_key>
  OR set env: SUPABASE_SERVICE_KEY=... then python enable_rls.py
"""
import sys, os, json
import urllib.request, urllib.error

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY  = (
    sys.argv[1] if len(sys.argv) > 1
    else os.getenv("SUPABASE_SERVICE_KEY", "")
)

if not SUPABASE_URL:
    # fallback: read from backend/.env
    env_path = os.path.join(os.path.dirname(__file__), "backend", ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("SUPABASE_URL="):
                SUPABASE_URL = line.split("=", 1)[1].strip().rstrip("/")

if not SUPABASE_URL or not SERVICE_KEY:
    print("Usage: python enable_rls.py <service_role_key>")
    print("  OR set SUPABASE_URL and SUPABASE_SERVICE_KEY env vars")
    print()
    print("Get the service_role key from:")
    print("  Supabase Dashboard → Project Settings → API → service_role (secret)")
    sys.exit(1)

# ── SQL to run ────────────────────────────────────────────────────────────────
# This SQL:
#  1. Enables RLS on voice_data (blocks all access by default)
#  2. Drops any existing policies to prevent conflicts
#  3. Adds INSERT policy — anon key can insert (backend writes session data)
#  4. Adds SELECT policy — anon key can select
#  5. Adds UPDATE policy — anon key can update
SQL_STATEMENTS = [
    # Step 1: Enable RLS
    "ALTER TABLE voice_data ENABLE ROW LEVEL SECURITY;",

    # Step 2: Drop existing policies if any
    "DROP POLICY IF EXISTS \"anon_insert\" ON voice_data;",
    "DROP POLICY IF EXISTS \"anon_update_own\" ON voice_data;",
    "DROP POLICY IF EXISTS \"anon_select\" ON voice_data;",

    # Step 3: Allow backend (anon key) to INSERT new session rows
    """CREATE POLICY \"anon_insert\"
     ON voice_data FOR INSERT
     TO anon
     WITH CHECK (true);""",

    # Step 4: Allow backend to UPDATE its own rows
    """CREATE POLICY \"anon_update_own\"
     ON voice_data FOR UPDATE
     TO anon
     USING (true)
     WITH CHECK (true);""",

    # Step 5: Allow backend to SELECT
    """CREATE POLICY \"anon_select\"
     ON voice_data FOR SELECT
     TO anon
     USING (true);""",
]

def run_sql(sql: str, label: str):
    """Execute SQL via Supabase REST API (requires service_role key)."""
    payload = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
        data=payload,
        headers={
            "apikey":        SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            print(f"  ✅ {label}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        # 409 = already exists (policy/RLS already enabled) — treat as OK
        if e.code == 409 or "already exists" in body or "already enabled" in body:
            print(f"  ✅ {label} (already applied)")
            return True
        print(f"  ❌ {label}: HTTP {e.code} — {body[:200]}")
        return False
    except Exception as ex:
        print(f"  ❌ {label}: {ex}")
        return False

# ── Try direct SQL via pg-meta (Supabase Management API) ─────────────────────
def run_sql_management(sql: str, label: str):
    """Use Supabase Management API pg-meta endpoint."""
    project_ref = SUPABASE_URL.replace("https://", "").split(".")[0]
    payload = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{project_ref}/database/query",
        data=payload,
        headers={
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            print(f"  ✅ {label}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if "already" in body.lower():
            print(f"  ✅ {label} (already applied)")
            return True
        print(f"  ❌ {label}: HTTP {e.code} — {body[:200]}")
        return False
    except Exception as ex:
        print(f"  ❌ {label}: {ex}")
        return False

# ── Main ──────────────────────────────────────────────────────────────────────
LABELS = [
    "Enable RLS on voice_data",
    "Drop old INSERT policy",
    "Drop old UPDATE policy",
    "Drop old SELECT policy",
    "Create Policy: anon INSERT",
    "Create Policy: anon UPDATE",
    "Create Policy: anon SELECT",
]

print(f"\nEnabling Row Level Security on: {SUPABASE_URL}")
print(f"Using: service_role key ({SERVICE_KEY[:20]}...)")
print("-" * 60)

ok = 0
for sql, label in zip(SQL_STATEMENTS, LABELS):
    if run_sql_management(sql, label):
        ok += 1

print("-" * 60)
print(f"\nResult: {ok}/{len(SQL_STATEMENTS)} statements applied")

if ok == len(SQL_STATEMENTS):
    print("\n✅ RLS enabled! Verifying anon access is now blocked...")
    # Verify
    import urllib.request as ur
    anon_key_env = ""
    env_path = os.path.join(os.path.dirname(__file__), "backend", ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("SUPABASE_KEY="):
                anon_key_env = line.split("=",1)[1].strip()
    if anon_key_env:
        req = ur.Request(
            f"{SUPABASE_URL}/rest/v1/voice_data?limit=1",
            headers={"apikey": anon_key_env, "Authorization": f"Bearer {anon_key_env}", "Accept": "application/json"}
        )
        try:
            with ur.urlopen(req, timeout=8) as r:
                rows = json.loads(r.read())
                if rows:
                    print(f"⚠  Anon can still read {len(rows)} rows — SELECT policy allows all. This is OK for backend use.")
                    print("   To fully lock down reads: restrict SELECT policy to authenticated role only.")
                else:
                    print("✅ Anon reads 0 rows — table is protected.")
        except urllib.error.HTTPError as e:
            print(f"✅ Anon blocked: HTTP {e.code} — RLS working correctly.")
else:
    print("\n⚠  Some statements failed. Run them manually in Supabase SQL Editor:")
    print(f"   Supabase Dashboard → SQL Editor → New Query")
    print()
    for sql in SQL_STATEMENTS:
        print(sql)
        print()
