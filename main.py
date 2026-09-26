import os
import shutil
import uuid
import time
import hashlib
import io
import warnings
import ipaddress
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from PIL import Image
from starlette.concurrency import run_in_threadpool

import jwt
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

import database
import trust_engine

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    warnings.warn(
        "SECURITY NOTICE: JWT_SECRET_KEY environment variable is not configured. "
        "Falling back to development key. In production, configure a strong secret key."
    )
    SECRET_KEY = "daily_bugle_secret_super_key_2026_x"

ALGORITHM = "HS256"
COOKIE_NAME = "bugle_session"

app = FastAPI(title="The Daily Bugle News & Trust Engine")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
is_serverless = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("NETLIFY"))
UPLOADS_DIR = "/tmp/uploads" if is_serverless else os.path.join(STATIC_DIR, "uploads")

try:
    os.makedirs(UPLOADS_DIR, exist_ok=True)
except Exception:
    pass

try:
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
except Exception:
    pass

# Initialize database
database.init_db()

# Mount static assets
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- In-Memory Sliding Window Rate Limiter with Auto-Eviction ---
REPORT_RATE_LIMIT = defaultdict(list)
OTP_RATE_LIMIT = defaultdict(list)
SUBNET_RATE_LIMIT = defaultdict(list)

def check_rate_limit(store: dict, key: str, max_calls: int, window_seconds: int) -> bool:
    """Returns True if within limit, False if rate limited. Automatically evicts expired entries."""
    now = time.time()
    valid_times = [t for t in store.get(key, []) if now - t < window_seconds]
    if valid_times:
        store[key] = valid_times
    elif key in store:
        del store[key]

    # Bound memory by pruning stale keys when cache grows large
    if len(store) > 10000:
        stale_keys = [k for k, v in list(store.items())[:500] if not v or now - v[-1] >= window_seconds]
        for k in stale_keys:
            store.pop(k, None)

    if len(valid_times) >= max_calls:
        return False
    if key not in store:
        store[key] = []
    store[key].append(now)
    return True

def get_client_ip(request: Request) -> str:
    """Extracts client IP address safely, preventing spoofed header injections."""
    forwarded = request.headers.get("X-Forwarded-For")
    raw_ip = ""
    if forwarded:
        raw_ip = forwarded.split(",")[0].strip()
    elif request.client and request.client.host:
        raw_ip = request.client.host
    else:
        raw_ip = "127.0.0.1"
    try:
        ipaddress.ip_address(raw_ip)
        return raw_ip
    except ValueError:
        return request.client.host if (request.client and request.client.host) else "127.0.0.1"


# --- Session & Authentication Helpers ---

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=24))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            return None
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        if user:
            return dict(user)
    except Exception:
        return None
    return None


# --- HTML Page Routes ---

@app.get("/")
def serve_index():
    """Publicly accessible homepage and wire feed."""
    return FileResponse(os.path.join(TEMPLATES_DIR, "index.html"))

@app.get("/incident/{incident_id}")
def serve_incident_detail_page(incident_id: int):
    """Publicly accessible deep-dive article page."""
    return FileResponse(os.path.join(TEMPLATES_DIR, "incident_detail.html"))

@app.get("/login")
def serve_login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return FileResponse(os.path.join(TEMPLATES_DIR, "login.html"))

@app.get("/report")
def serve_report_page(request: Request):
    """Protected reporting view: requires an active user session."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login?redirect=/report", status_code=302)
    return FileResponse(os.path.join(TEMPLATES_DIR, "report.html"))

@app.get("/desk")
def serve_desk_page(request: Request):
    """Protected authority triage view: requires EDITOR clearance."""
    user = get_current_user(request)
    if not user or user.get("role") != "EDITOR":
        return RedirectResponse(url="/login?redirect=/desk", status_code=302)
    return FileResponse(os.path.join(TEMPLATES_DIR, "desk.html"))

@app.get("/dispatch")
def serve_dispatch_page(request: Request):
    """Protected authority Emergency Dispatch console: requires EDITOR or DISPATCHER clearance."""
    user = get_current_user(request)
    if not user or user.get("role") not in ["EDITOR", "DISPATCHER"]:
        return RedirectResponse(url="/login?redirect=/dispatch", status_code=302)
    return FileResponse(os.path.join(TEMPLATES_DIR, "dispatch.html"))

@app.get("/incident/{incident_id}/bulletin")
def serve_bulletin_page(incident_id: int):
    """Publicly accessible printable Security Advisory SITREP bulletin."""
    return FileResponse(os.path.join(TEMPLATES_DIR, "bulletin.html"))


# --- OTP & Authentication Endpoints ---

@app.post("/api/auth/send-otp")
def send_otp(identifier: str = Form(...), purpose: str = Form("REGISTER")):
    """Generates a 6-digit OTP code and prints it to the terminal for verification."""
    clean_id = identifier.strip().lower()
    if not clean_id:
        return JSONResponse({"error": "Email or phone number is required."}, status_code=400)
    
    # Rate limit check: max 4 OTP requests per 10 minutes
    if not check_rate_limit(OTP_RATE_LIMIT, clean_id, max_calls=4, window_seconds=600):
        return JSONResponse({"error": "Too many verification requests. Please wait 10 minutes before requesting again."}, status_code=429)

    code = database.create_otp_token(clean_id, purpose=purpose)
    return {
        "status": "success",
        "message": f"Verification code dispatched to {clean_id}. (Check terminal for development preview)",
        "identifier": clean_id
    }

@app.post("/api/auth/phone/send-otp")
async def send_phone_otp(request: Request):
    """Generates and dispatches a 6-digit access code for mobile phone sign-in."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    phone = data.get("phone", "").strip()
    if not phone:
        form = await request.form()
        phone = form.get("phone", "").strip()

    digits = [c for c in phone if c.isdigit()]
    if len(digits) < 8:
        return JSONResponse({"error": "Please enter a valid mobile number with at least 8 digits."}, status_code=400)

    clean_phone = phone.replace(" ", "")

    # Rate limit check: max 4 OTP requests per 10 minutes
    if not check_rate_limit(OTP_RATE_LIMIT, clean_phone, max_calls=4, window_seconds=600):
        return JSONResponse({"error": "Too many verification requests. Please wait 10 minutes before requesting again."}, status_code=429)

    code = database.create_otp_token(clean_phone, purpose="PHONE_AUTH", expiry_minutes=10)
    return {
        "status": "success",
        "message": f"Dispatch token sent to {clean_phone}. Check your server console for the 6-digit code!",
        "phone": clean_phone,
        "dev_code": code if os.getenv("DEBUG", "True").lower() == "true" else None
    }

@app.post("/api/auth/phone/verify-otp")
async def verify_phone_otp(request: Request):
    """Verifies the 6-digit code and authenticates the citizen reporter session."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    phone = data.get("phone", "").strip()
    code = data.get("code", "").strip()
    name = data.get("name", "").strip()

    if not phone or not code:
        form = await request.form()
        phone = form.get("phone", phone).strip()
        code = form.get("code", code).strip()
        name = form.get("name", name).strip()

    clean_phone = phone.replace(" ", "")
    if not database.verify_otp_token(clean_phone, code, purpose="PHONE_AUTH"):
        return JSONResponse({"error": "Invalid or expired 6-digit verification code."}, status_code=400)

    local_user = database.get_or_create_phone_user(clean_phone, full_name=name)
    jwt_token = create_access_token({"sub": local_user["username"], "user_id": local_user["id"]})
    response = JSONResponse({
        "status": "success",
        "user": local_user,
        "message": f"Welcome back, {local_user['name']}! Press clearance activated."
    })
    response.set_cookie(key=COOKIE_NAME, value=jwt_token, httponly=True, samesite="lax", max_age=86400)
    return response

@app.get("/api/config/supabase")
def get_supabase_config():
    """Exposes public Supabase parameters for browser-side SDK initialization."""
    pub_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
    return {
        "url": database.SUPABASE_URL,
        "publishable_key": pub_key,
        "storage_bucket": database.SUPABASE_STORAGE_BUCKET,
        "configured": bool(database.SUPABASE_URL and pub_key)
    }

@app.post("/api/auth/supabase-sync")
async def supabase_auth_sync(request: Request):
    """Validates client-side Supabase token and creates the local session cookie."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON payload provided."}, status_code=400)

    access_token = data.get("access_token")
    if not access_token:
        return JSONResponse({"error": "Missing access token."}, status_code=400)

    local_user = None

    # 1. Authoritative verification via Supabase SDK if connected
    if database.supabase:
        try:
            user_res = database.supabase.auth.get_user(access_token)
            if user_res and user_res.user:
                sb_user = user_res.user
                email_or_phone = sb_user.email or sb_user.phone or f"user_{sb_user.id[:8]}"
                metadata = getattr(sb_user, "user_metadata", {}) or {}
                full_name = metadata.get("full_name") or metadata.get("name") or email_or_phone.split("@")[0]
                local_user = database.sync_supabase_user(sb_user.id, email_or_phone, full_name)
        except Exception as verify_err:
            print(f"[Supabase Sync] Verification warning: {verify_err}")

    # 2. Resilient fallback to client user object if server-side gateway was offline
    if not local_user and data.get("user"):
        u = data["user"]
        uid = u.get("id") or f"usr_{uuid.uuid4().hex[:8]}"
        email_or_phone = u.get("email") or u.get("phone") or f"user_{uid[:6]}"
        meta = u.get("user_metadata") or {}
        full_name = meta.get("full_name") or meta.get("name") or email_or_phone.split("@")[0]
        local_user = database.sync_supabase_user(uid, email_or_phone, full_name)

    if not local_user:
        return JSONResponse({"error": "Could not validate or synchronize Supabase account."}, status_code=401)

    jwt_token = create_access_token({"sub": local_user["username"], "user_id": local_user["id"]})
    response = JSONResponse({"status": "success", "user": local_user})
    response.set_cookie(key=COOKIE_NAME, value=jwt_token, httponly=True, samesite="lax", max_age=86400)
    return response

@app.post("/api/auth/supabase-signup")
async def supabase_signup(request: Request):
    """Bypasses client email rate limits by creating and auto-confirming user via Supabase Admin API."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid request payload."}, status_code=400)

    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    name = data.get("name", "").strip() or email.split("@")[0]

    if not email or "@" not in email:
        return JSONResponse({"error": "A valid email address is required."}, status_code=400)
    if len(password) < 6:
        return JSONResponse({"error": "Password must be at least 6 characters long."}, status_code=400)

    # 1. Attempt creation via Supabase Admin API (Bypasses email rate limits and auto-confirms)
    if database.supabase:
        try:
            admin_res = database.supabase.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"full_name": name, "name": name}
            })
            if admin_res and admin_res.user:
                sb_user = admin_res.user
                local_user = database.sync_supabase_user(sb_user.id, email, name)
                jwt_token = create_access_token({"sub": local_user["username"], "user_id": local_user["id"]})
                response = JSONResponse({
                    "status": "success",
                    "user": local_user,
                    "message": "Account created and verified! Welcome to the newsroom."
                })
                response.set_cookie(key=COOKIE_NAME, value=jwt_token, httponly=True, samesite="lax", max_age=86400)
                return response
        except Exception as e:
            err_msg = str(e)
            if "already registered" in err_msg.lower() or "unique" in err_msg.lower():
                return JSONResponse({"error": "An account with this email already exists. Please sign in."}, status_code=400)
            return JSONResponse({"error": f"Supabase registration error: {err_msg}"}, status_code=400)

    # 2. Local database fallback if Supabase cloud is unreachable
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return JSONResponse({"error": "An account with this email already exists. Please sign in."}, status_code=400)

    user_id = f"usr_{uuid.uuid4().hex[:8]}"
    pwd_hash = database.hash_password(password)
    now = datetime.utcnow().isoformat()
    username = email.split("@")[0].lower().replace(" ", "_")

    cursor.execute("""
        INSERT INTO users (id, username, name, email, phone, password_hash, role, is_verified, trust_score, strike_count, is_quarantined, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'CITIZEN', 1, 0.60, 0, 0, ?)
    """, (user_id, username, name, email, email, pwd_hash, now))
    conn.commit()
    conn.close()

    jwt_token = create_access_token({"sub": username, "user_id": user_id})
    response = JSONResponse({"status": "success", "message": "Account created successfully!"})
    response.set_cookie(key=COOKIE_NAME, value=jwt_token, httponly=True, samesite="lax", max_age=86400)
    return response

@app.post("/api/auth/register")
def register_user(
    username: str = Form(...),
    name: str = Form(...),
    identifier: str = Form(...),  # Email or Phone
    otp_code: str = Form(...),
    password: str = Form(...),
    role: str = Form("CITIZEN")
):
    clean_id = identifier.strip().lower()
    clean_user = username.strip()

    # Verify OTP token before creating the account
    if not database.verify_otp_token(clean_id, otp_code, purpose="REGISTER"):
        return JSONResponse({"error": "Invalid or expired verification code."}, status_code=400)

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?", (clean_user, clean_id))
    if cursor.fetchone():
        conn.close()
        return JSONResponse({"error": "Username or contact identifier already registered."}, status_code=400)

    user_id = f"usr_{uuid.uuid4().hex[:8]}"
    pwd_hash = database.hash_password(password)
    now = datetime.utcnow().isoformat()
    valid_role = "EDITOR" if role == "EDITOR" else "CITIZEN"

    cursor.execute("""
    INSERT INTO users (id, username, name, email, phone, password_hash, role, is_verified, trust_score, strike_count, is_quarantined, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0.50, 0, 0, ?)
    """, (user_id, clean_user, name.strip(), clean_id, clean_id, pwd_hash, valid_role, now))
    conn.commit()
    conn.close()

    token = create_access_token({"sub": clean_user})
    response = JSONResponse({"status": "success", "message": "Account verified and registered successfully"})
    response.set_cookie(key=COOKIE_NAME, value=token, httponly=True, samesite="lax", max_age=86400)
    return response

@app.post("/api/auth/login")
def login_user(username: str = Form(...), password: str = Form(...)):
    conn = database.get_connection()
    cursor = conn.cursor()
    # Allow logging in via username or email
    cursor.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username.strip(), username.strip().lower()))
    user = cursor.fetchone()
    conn.close()

    if not user or not database.verify_password(password, user["password_hash"]):
        return JSONResponse({"error": "Invalid credentials provided."}, status_code=401)

    token = create_access_token({"sub": user["username"]})
    response = JSONResponse({
        "status": "success",
        "user": {
            "username": user["username"],
            "name": user["name"],
            "role": user["role"],
            "trust_score": user["trust_score"]
        }
    })
    response.set_cookie(key=COOKIE_NAME, value=token, httponly=True, samesite="lax", max_age=86400)
    return response

@app.post("/api/auth/logout")
def logout_user():
    response = JSONResponse({"status": "success", "message": "Session invalidated"})
    response.delete_cookie(key=COOKIE_NAME)
    return response

@app.get("/api/auth/me")
def current_user_session(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"authenticated": False})
    return {
        "authenticated": True,
        "username": user["username"],
        "name": user["name"],
        "role": user["role"],
        "trust_score": user["trust_score"],
        "strike_count": user["strike_count"],
        "is_quarantined": bool(user["is_quarantined"])
    }


@app.get("/api/profile/me")
def get_my_profile(request: Request):
    """Returns the authenticated user's full profile: stats, report history, and trust breakdown."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conn = database.get_connection()
    cursor = conn.cursor()

    # Full report history with linked incident titles and status
    cursor.execute("""
        SELECT
            r.id,
            r.incident_id,
            r.category,
            r.description,
            r.latitude,
            r.longitude,
            r.injuries,
            r.threat_state,
            r.image_url,
            r.created_at,
            i.title AS incident_title,
            i.status AS incident_status,
            i.confidence_score AS incident_confidence
        FROM reports r
        LEFT JOIN incidents i ON r.incident_id = i.id
        WHERE r.user_id = ?
        ORDER BY r.created_at DESC
        LIMIT 50
    """, (user["id"],))
    reports = [dict(r) for r in cursor.fetchall()]

    # Aggregate stats
    cursor.execute("SELECT COUNT(*) FROM reports WHERE user_id = ?", (user["id"],))
    total_reports = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT r.incident_id)
        FROM reports r
        JOIN incidents i ON r.incident_id = i.id
        WHERE r.user_id = ? AND i.status = 'VERIFIED'
    """, (user["id"],))
    verified_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT r.incident_id)
        FROM reports r
        JOIN incidents i ON r.incident_id = i.id
        WHERE r.user_id = ? AND i.status = 'BUSTED'
    """, (user["id"],))
    busted_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM disputes WHERE user_id = ?", (user["id"],))
    dispute_count = cursor.fetchone()[0]

    conn.close()

    # Trust score label
    ts = float(user["trust_score"])
    if ts >= 0.90:
        trust_label = "Elite Correspondent"
        trust_tier = "elite"
    elif ts >= 0.75:
        trust_label = "Verified Stringer"
        trust_tier = "verified"
    elif ts >= 0.55:
        trust_label = "Community Reporter"
        trust_tier = "community"
    elif ts >= 0.35:
        trust_label = "Under Review"
        trust_tier = "review"
    else:
        trust_label = "Quarantine Risk"
        trust_tier = "risk"

    # Achievements / badges
    achievements = []
    if total_reports >= 1:
        achievements.append({"icon": "📰", "label": "First Dispatch", "desc": "Filed your first report"})
    if total_reports >= 5:
        achievements.append({"icon": "🔍", "label": "Field Stringer", "desc": "5+ reports filed"})
    if total_reports >= 20:
        achievements.append({"icon": "🏆", "label": "Senior Correspondent", "desc": "20+ reports filed"})
    if verified_count >= 1:
        achievements.append({"icon": "✅", "label": "Verified Tipster", "desc": "1+ report led to a verified incident"})
    if verified_count >= 5:
        achievements.append({"icon": "⚡", "label": "Ground Truth Agent", "desc": "5+ verified incident contributions"})
    if ts >= 0.90:
        achievements.append({"icon": "🌟", "label": "Press Elite", "desc": "Trust score above 90%"})
    if user["strike_count"] == 0 and total_reports >= 3:
        achievements.append({"icon": "🛡️", "label": "Clean Record", "desc": "Zero strikes on file"})
    if dispute_count >= 1:
        achievements.append({"icon": "🚩", "label": "Fact Challenger", "desc": "Filed an on-scene dispute"})

    return {
        "user": {
            "id": user["id"],
            "username": user["username"],
            "name": user["name"],
            "email": user.get("email", ""),
            "phone": user.get("phone", ""),
            "role": user["role"],
            "trust_score": ts,
            "trust_score_pct": round(ts * 100),
            "trust_label": trust_label,
            "trust_tier": trust_tier,
            "strike_count": user["strike_count"],
            "is_quarantined": bool(user["is_quarantined"]),
            "is_verified": bool(user["is_verified"]),
            "created_at": user["created_at"],
        },
        "stats": {
            "total_reports": total_reports,
            "verified_count": verified_count,
            "busted_count": busted_count,
            "dispute_count": dispute_count,
            "accuracy_rate": round((verified_count / total_reports * 100) if total_reports > 0 else 0),
        },
        "achievements": achievements,
        "reports": reports,
    }

@app.get("/api/incidents")
def get_incidents(view: str = "wire"):
    """Public incident feed queries with 5-tier classification and freshness decay."""
    conn = database.get_connection()
    cursor = conn.cursor()

    if view == "wire":
        # Wire highlights credible signals: VERIFIED, CORROBORATED, COMMUNITY, and active INVESTIGATING responses
        cursor.execute("""
            SELECT * FROM incidents 
            WHERE status IN ('VERIFIED', 'CORROBORATED', 'COMMUNITY', 'INVESTIGATING')
            ORDER BY is_lethal_priority DESC, updated_at DESC
        """)
    elif view == "unverified":
        # Community Audit Queue: Incoming signals undergoing verification
        cursor.execute("""
            SELECT * FROM incidents 
            WHERE status IN ('UNVERIFIED', 'REVIEW', 'SUSPICIOUS')
            ORDER BY is_lethal_priority DESC, updated_at DESC
        """)
    elif view == "radar":
        cursor.execute("""
            SELECT * FROM incidents 
            WHERE is_spatial = 1 AND status IN ('VERIFIED', 'CORROBORATED', 'COMMUNITY', 'INVESTIGATING')
            ORDER BY is_lethal_priority DESC, confidence_score DESC
        """)
    elif view == "graveyard":
        cursor.execute("SELECT * FROM incidents WHERE status = 'BUSTED' ORDER BY updated_at DESC")
    elif view == "desk":
        # Authority Triage & Dispatch Console: strictly prioritize HAZMAT, mass casualties, and high-threat incidents
        cursor.execute("""
            SELECT * FROM incidents 
            ORDER BY 
                is_lethal_priority DESC, 
                CASE WHEN injuries = 'CONFIRMED' THEN 1 WHEN injuries = 'SUSPECTED' THEN 2 ELSE 3 END, 
                confidence_score DESC, 
                updated_at DESC
        """)
    else:
        cursor.execute("SELECT * FROM incidents WHERE status != 'BUSTED' ORDER BY is_lethal_priority DESC, updated_at DESC")

    raw_incidents = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Apply freshness score decay based on elapsed activity window and attach credibility matrix
    decayed_incidents = [trust_engine.apply_time_decay(inc) for inc in raw_incidents]
    for inc in decayed_incidents:
        if inc.get("credibility_matrix_json"):
            try:
                inc["credibility_matrix"] = json.loads(inc["credibility_matrix_json"])
            except Exception:
                inc["credibility_matrix"] = trust_engine.compute_credibility_matrix(inc["id"])
        else:
            inc["credibility_matrix"] = trust_engine.compute_credibility_matrix(inc["id"])
    return decayed_incidents

@app.get("/api/incidents/{incident_id}")
def get_single_incident(incident_id: int):
    """Fetches complete incident metadata, full article, corroborating reports, and on-scene disputes."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    incident = cursor.fetchone()
    if not incident:
        conn.close()
        raise HTTPException(status_code=404, detail="Incident article not found")

    incident_dict = trust_engine.apply_time_decay(dict(incident))
    
    # Retrieve connected eyewitness reports
    cursor.execute("""
        SELECT r.*, u.name as reporter_name, u.role as reporter_role, u.trust_score as reporter_trust
        FROM reports r
        LEFT JOIN users u ON r.user_id = u.id
        WHERE r.incident_id = ?
        ORDER BY r.created_at ASC
    """, (incident_id,))
    reports = [dict(r) for r in cursor.fetchall()]

    # Retrieve on-scene citizen disputes
    disputes = database.get_incident_disputes(incident_id)
    conn.close()

    incident_dict["reports"] = reports
    incident_dict["disputes"] = disputes
    if incident_dict.get("credibility_matrix_json"):
        try:
            incident_dict["credibility_matrix"] = json.loads(incident_dict["credibility_matrix_json"])
        except Exception:
            incident_dict["credibility_matrix"] = trust_engine.compute_credibility_matrix(incident_id)
    else:
        incident_dict["credibility_matrix"] = trust_engine.compute_credibility_matrix(incident_id)
    return incident_dict

@app.post("/api/reports")
async def submit_citizen_report(
    request: Request,
    category: str = Form(...),
    description: str = Form(...),
    latitude: float = Form(0.0),
    longitude: float = Form(0.0),
    is_spatial: int = Form(1),
    injuries: str = Form("NONE"),
    threat_state: str = Form("ACTIVE"),
    responders_present: str = Form("NONE"),
    image: UploadFile = File(None)
):
    """Emergency intake route: validates input bounds, identity or creates guest record, applies sliding-window rate limit, and captures triage fields."""
    # 1. Geographic Bounds Validation
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return JSONResponse({
            "error": "Invalid geographical coordinates. Latitude must be between -90 and 90, Longitude between -180 and 180."
        }, status_code=400)

    # 2. Category Whitelist Validation
    ALLOWED_CATEGORIES = {"Fire", "Obstruction", "Assault", "Civic", "Disaster", "Explosion"}
    cleaned_category = category.strip().capitalize() if category else ""
    if cleaned_category not in ALLOWED_CATEGORIES:
        return JSONResponse({
            "error": f"Invalid incident category '{category}'. Permitted categories are: {', '.join(sorted(ALLOWED_CATEGORIES))}."
        }, status_code=400)
    category = cleaned_category

    user = get_current_user(request)
    is_guest = False

    # Extract client IP and device fingerprint for Anti-Sybil protection
    client_ip = get_client_ip(request)
    device_hash = request.headers.get("User-Agent", "unknown_device")[:120]
    subnet = client_ip.rsplit(".", 1)[0] + ".0/24" if "." in client_ip else client_ip.split(":")[0]

    if not user:
        is_guest = True
        guest_id = f"guest_{hashlib.md5(client_ip.encode()).hexdigest()[:8]}"
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (guest_id,))
        guest_row = cursor.fetchone()
        if not guest_row:
            now_iso = datetime.utcnow().isoformat()
            cursor.execute("""
                INSERT OR IGNORE INTO users (id, username, name, email, phone, password_hash, role, is_verified, trust_score, strike_count, is_quarantined, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'CITIZEN', 0, 0.45, 0, 0, ?)
            """, (guest_id, f"guest_{guest_id[-4:]}", "Anonymous Witness", f"{guest_id}@guest.local", "UNVERIFIED", "NO_PWD", now_iso))
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE id = ?", (guest_id,))
            guest_row = cursor.fetchone()
        conn.close()
        user = dict(guest_row)

        # In-memory sliding-window rate limit for guest submissions: max 2 per 5 minutes per IP
        if not check_rate_limit(REPORT_RATE_LIMIT, f"guest_ip_{client_ip}", max_calls=2, window_seconds=300):
            return JSONResponse({
                "error": "Emergency submission limit reached for guest IP. Please sign in or wait 5 minutes before filing another report."
            }, status_code=429)
    else:
        # In-memory sliding-window rate limit: max 3 reports per user per 5 minutes
        if not check_rate_limit(REPORT_RATE_LIMIT, user["id"], max_calls=3, window_seconds=300):
            return JSONResponse({
                "error": "Submission rate limit reached: You may submit at most 3 reports every 5 minutes."
            }, status_code=429)

    # Subnet sliding-window rate limit: max 6 submissions per /24 subnet per 5 minutes
    if not check_rate_limit(SUBNET_RATE_LIMIT, subnet, max_calls=6, window_seconds=300):
        return JSONResponse({
            "error": "Network subnet rate limit reached: Too many reports submitted from your IP subnet. Anti-Sybil protection active."
        }, status_code=429)

    image_rel_url = ""
    file_bytes = None
    content_type = "image/jpeg"
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB limit
    if image and image.filename:
        file_bytes = await image.read()
        if file_bytes:
            if len(file_bytes) > MAX_IMAGE_SIZE:
                return JSONResponse({
                    "error": "Uploaded image exceeds the 10MB maximum file size limit."
                }, status_code=413)
            # Verify image format and header integrity using Pillow
            try:
                with Image.open(io.BytesIO(file_bytes)) as pil_img:
                    pil_img.verify()
            except Exception:
                return JSONResponse({
                    "error": "Invalid or corrupted image format. Please upload a valid JPEG, PNG, or WebP photo."
                }, status_code=400)

            content_type = image.content_type or "image/jpeg"
            # 1. Attempt Supabase Cloud Storage upload
            supabase_cdn_url = database.upload_evidence_to_supabase(file_bytes, image.filename, content_type)
            if supabase_cdn_url:
                image_rel_url = supabase_cdn_url
            else:
                # 2. Local resilient fallback
                safe_filename = f"{int(datetime.utcnow().timestamp() * 1000)}_{image.filename.replace(' ', '_')}"
                save_path = os.path.join(UPLOADS_DIR, safe_filename)
                with open(save_path, "wb") as buffer:
                    buffer.write(file_bytes)
                image_rel_url = f"/static/uploads/{safe_filename}"

    # Asynchronously offload thread-blocking engine processing to threadpool
    result = await run_in_threadpool(
        trust_engine.process_new_report,
        user_id=user["id"],
        category=category,
        description=description,
        lat=latitude,
        lng=longitude,
        is_spatial=is_spatial,
        image_url=image_rel_url,
        image_bytes=file_bytes,
        mime_type=content_type,
        injuries=injuries,
        threat_state=threat_state,
        responders_present=responders_present,
        client_ip=client_ip,
        device_hash=device_hash
    )
    result["is_guest"] = is_guest
    return JSONResponse(result)

@app.post("/api/incidents/{incident_id}/corroborate")
async def corroborate_incident(
    incident_id: int,
    request: Request,
    description: str = Form(...),
    image: UploadFile = File(None)
):
    """Allows authenticated citizens to add eyewitness corroborations directly to an existing incident."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Verified sign-in required to corroborate incidents."}, status_code=401)

    # In-memory rate limiting: max 4 corroborations per 5 minutes
    if not check_rate_limit(REPORT_RATE_LIMIT, user["id"], max_calls=4, window_seconds=300):
        return JSONResponse({"error": "Corroboration rate limit reached. Please wait before submitting more observations."}, status_code=429)

    client_ip = get_client_ip(request)
    device_hash = request.headers.get("User-Agent", "unknown_device")[:120]

    image_rel_url = ""
    file_bytes = None
    content_type = "image/jpeg"
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB limit
    if image and image.filename:
        file_bytes = await image.read()
        if file_bytes:
            if len(file_bytes) > MAX_IMAGE_SIZE:
                return JSONResponse({"error": "Uploaded image exceeds the 10MB maximum file size limit."}, status_code=413)
            try:
                with Image.open(io.BytesIO(file_bytes)) as pil_img:
                    pil_img.verify()
            except Exception:
                return JSONResponse({"error": "Invalid or corrupted image format. Please upload a valid JPEG, PNG, or WebP photo."}, status_code=400)

            content_type = image.content_type or "image/jpeg"
            supabase_cdn_url = database.upload_evidence_to_supabase(file_bytes, image.filename, content_type)
            if supabase_cdn_url:
                image_rel_url = supabase_cdn_url
            else:
                safe_filename = f"corr_{int(datetime.utcnow().timestamp() * 1000)}_{image.filename.replace(' ', '_')}"
                save_path = os.path.join(UPLOADS_DIR, safe_filename)
                with open(save_path, "wb") as buffer:
                    buffer.write(file_bytes)
                image_rel_url = f"/static/uploads/{safe_filename}"

    # Asynchronously offload thread-blocking engine processing to threadpool
    result = await run_in_threadpool(
        trust_engine.corroborate_existing_incident,
        incident_id=incident_id,
        user_id=user["id"],
        note=description,
        image_url=image_rel_url,
        image_bytes=file_bytes,
        mime_type=content_type,
        client_ip=client_ip,
        device_hash=device_hash
    )
    return JSONResponse(result)

@app.get("/api/dispatch/analytics")
def get_dispatch_analytics(request: Request):
    """Returns real-time emergency dispatch metrics and detects tactical swatting/diversion bursts."""
    conn = database.get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, category, latitude, longitude, confidence_score, status, is_lethal_priority, created_at, updated_at
        FROM incidents
        WHERE status != 'BUSTED'
        ORDER BY updated_at DESC LIMIT 50
    """)
    active_incidents = [dict(r) for r in cursor.fetchall()]
    conn.close()

    now = datetime.now()
    recent_high_severity = []
    for inc in active_incidents:
        try:
            ts = inc.get("updated_at") or inc.get("created_at")
            inc_dt = datetime.fromisoformat(ts)
            diff_min = (now - inc_dt).total_seconds() / 60.0
            if diff_min <= 15.0 and (inc.get("confidence_score", 0) >= 65 or inc.get("is_lethal_priority") == 1):
                recent_high_severity.append(inc)
        except Exception:
            pass

    # Check for geographic dispersion: if 3+ high-severity events are >2.5km apart, trigger swatting warning
    swatting_warning = False
    warning_message = ""
    if len(recent_high_severity) >= 3:
        dispersed = False
        for i in range(len(recent_high_severity)):
            for j in range(i + 1, len(recent_high_severity)):
                d = trust_engine.haversine_distance_meters(
                    recent_high_severity[i]["latitude"], recent_high_severity[i]["longitude"],
                    recent_high_severity[j]["latitude"], recent_high_severity[j]["longitude"]
                )
                if d >= 2500:
                    dispersed = True
                    break
        if dispersed:
            swatting_warning = True
            warning_message = "TACTICAL SWATTING / DIVERSION ALERT: 3+ high-severity incidents registered across divergent sectors within 15 minutes. Dispatchers must conduct secondary callback confirmation before committing physical units."

    return {
        "total_active": len(active_incidents),
        "recent_high_severity_count": len(recent_high_severity),
        "swatting_warning": swatting_warning,
        "warning_message": warning_message
    }

@app.post("/api/incidents/{incident_id}/dispute")
async def dispute_incident(
    incident_id: int,
    request: Request,
    note: str = Form(...)
):
    """Allows on-scene citizens to submit counter-evidence ('Nothing observed here'), deducting trust points."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Verified sign-in required to submit on-scene dispute."}, status_code=401)

    result = trust_engine.submit_scene_dispute(incident_id, user["id"], note)
    return JSONResponse(result)

@app.post("/api/incidents/{incident_id}/dispatch")
async def dispatch_incident(
    incident_id: int,
    request: Request,
    agency: str = Form(...),
    status: str = Form(...),
    notes: str = Form(""),
    mark_verified: bool = Form(False)
):
    """Authority Emergency Services dispatch state transition (Police 112, Fire 101, Ambulance 108). Protected by RBAC."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized: Emergency clearance required."}, status_code=401)
    if user.get("role") not in ["EDITOR", "DISPATCHER"]:
        return JSONResponse({"error": "Forbidden: Requires EDITOR or DISPATCHER authority clearance."}, status_code=403)

    conn = database.get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("SELECT status FROM incidents WHERE id = ?", (incident_id,))
    row = cursor.fetchone()
    current_status = row["status"] if row else "REVIEW"

    # Decouple exploratory dispatch from premature verification:
    # 1. 'ON_SCENE' arrival or 'RESOLVED' officially confirms the event as 'VERIFIED'
    # 2. 'DISPATCHED' or 'UNITS_EN_ROUTE' moves unverified signals to 'INVESTIGATING'
    # 3. BUSTED hoaxes cannot be revived by dispatch
    if status in ["ON_SCENE", "RESOLVED"] or mark_verified:
        if current_status != "BUSTED":
            cursor.execute("UPDATE incidents SET status = 'VERIFIED', updated_at = ? WHERE id = ?", (now, incident_id))
    elif status in ["DISPATCHED", "UNITS_EN_ROUTE"]:
        if current_status in ["REVIEW", "UNVERIFIED"]:
            cursor.execute("UPDATE incidents SET status = 'INVESTIGATING', updated_at = ? WHERE id = ?", (now, incident_id))
        else:
            cursor.execute("UPDATE incidents SET updated_at = ? WHERE id = ?", (now, incident_id))
    conn.commit()
    conn.close()

    updated_inc = database.update_incident_dispatch(incident_id, agency, status, notes)
    cred_matrix = trust_engine.compute_credibility_matrix(incident_id)
    updated_inc["credibility_matrix"] = cred_matrix
    
    # Broadcast to Supabase Realtime channel
    database.broadcast_realtime_event("dispatch-update", {
        "incident_id": incident_id,
        "agency": agency,
        "dispatch_status": status,
        "notes": notes,
        "credibility_matrix": cred_matrix
    })

    return {"status": "success", "incident": updated_inc}

@app.post("/api/incidents/{incident_id}/action")
def update_incident_action(incident_id: int, action: str = Form(...), request: Request = None):
    """Protected authority triage action."""
    user = get_current_user(request)
    if not user or user.get("role") != "EDITOR":
        return JSONResponse({"error": "Unauthorized: Editor credentials required."}, status_code=403)

    success = trust_engine.update_incident_status(incident_id, action)
    return {"success": success, "incident_id": incident_id, "action": action}


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 8000))
    print(f"Daily Bugle server running at http://{host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=True)