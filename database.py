import os
import sqlite3
import json
import random
import uuid
from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def get_db_path() -> str:
    """Returns path to SQLite database. Uses /tmp/bugle.db on serverless/read-only systems."""
    if os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("NETLIFY"):
        tmp_db = "/tmp/bugle.db"
        if not os.path.exists(tmp_db):
            src_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bugle.db")
            if os.path.exists(src_db):
                try:
                    import shutil
                    shutil.copy2(src_db, tmp_db)
                except Exception as e:
                    print(f"[DB Notice] Could not copy initial db to /tmp: {e}")
        return tmp_db
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "bugle.db")

DB_PATH = get_db_path()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SECRET_KEY")
    or os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY", "")
)
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "incident-evidence")

def seed_batch_incidents_6_to_9(conn=None):
    close_at_end = False
    if conn is None:
        conn = get_connection()
        close_at_end = True
    cursor = conn.cursor()
    now = datetime.now()

    incidents_to_add = [
        (
            6,
            "Chemical Gas Cylinder Leak at Mancheswar Industrial Estate",
            "Suspected chlorine gas leak at logistics warehouse; 200m safety perimeter initiated.",
            "Fire response teams and HAZMAT containment specialists responded to Mancheswar Industrial Estate after workers reported pungent choking fumes. Two individuals shifted to Capital Hospital.",
            "",
            "Civic",
            20.3124,
            85.8612,
            1,
            88,
            "VERIFIED",
            json.dumps([
                {"label": "Corroborated by 2 eyewitnesses", "value": "+18"},
                {"label": "Independent subnet diversity", "value": "+14"},
                {"label": "HAZMAT Priority Override", "value": "+15"},
            ]),
            2,
            2,
            "DISPATCHED",
            "FIRE",
            "Hazmat fire tender deployed with chemical protective equipment.",
            now.isoformat(),
            "CONFIRMED",
            "ACTIVE",
            "FIRE",
            0,
            1,
            0,
            now.isoformat(),
            now.isoformat(),
        ),
        (
            7,
            "Multi-Vehicle Pileup on Khandagiri Flyover Ramp",
            "Three-car collision with overturned pickup blocking inbound NH-16 lanes.",
            "Early morning multi-vehicle collision involving two passenger cars and a pickup truck paralyzed inbound traffic along Khandagiri ramp. Paramedics treating minor injuries on-site.",
            "",
            "Obstruction",
            20.2592,
            85.7891,
            1,
            92,
            "VERIFIED",
            json.dumps([
                {"label": "3 field corroborations logged", "value": "+22"},
                {"label": "Matching NH-16 GPS telemetry", "value": "+16"},
                {"label": "Emergency responders on-scene", "value": "+20"},
            ]),
            3,
            2,
            "ON_SCENE",
            "AMBULANCE",
            "Ambulance unit 108 and highway recovery crane active on-scene.",
            now.isoformat(),
            "SUSPECTED",
            "CONTAINED",
            "AMBULANCE",
            0,
            0,
            0,
            now.isoformat(),
            now.isoformat(),
        ),
        (
            8,
            "High-Voltage Wire Snap & Street Flooding at Nayapalli",
            "Overhead 11kV power distribution line dangling in waterlogged street.",
            "Urgent neighborhood alert regarding high-tension cable snap in rain-accumulated standing water near Behera Sahi. Grid isolation requested.",
            "",
            "Civic",
            20.2985,
            85.8123,
            1,
            68,
            "COMMUNITY",
            json.dumps([
                {"label": "Neighborhood alert cluster", "value": "+18"},
                {"label": "Awaiting grid substation confirmation", "value": "-8"},
            ]),
            2,
            2,
            "PENDING",
            "CIVIC",
            "Pending power grid substation shutdown verification.",
            None,
            "NONE",
            "ACTIVE",
            "NONE",
            0,
            1,
            0,
            now.isoformat(),
            now.isoformat(),
        ),
        (
            9,
            "Viral Hoax: Fictitious Kuakhai Barrage Breach Rumor",
            "Social media voice note claiming embankment collapse debunked by river telemetry.",
            "Circulating claim alleging structural breach at Kuakhai barrage investigated and debunked. Automated water gauge sensors confirm standard discharge levels.",
            "",
            "Disaster",
            20.4625,
            85.8828,
            1,
            12,
            "BUSTED",
            json.dumps([
                {"label": "Sensor telemetry contradicts claim", "value": "-35"},
                {"label": "Zero emergency call corroboration", "value": "-20"},
            ]),
            1,
            1,
            "RESOLVED",
            "CIVIC",
            "Debunked rumor. No responders committed.",
            now.isoformat(),
            "NONE",
            "CLEARED",
            "NONE",
            0,
            0,
            0,
            now.isoformat(),
            now.isoformat(),
        ),
    ]
    
    cursor.executemany(
        """
        INSERT OR REPLACE INTO incidents (
            id, title, summary, full_article, primary_image, category, latitude, longitude,
            is_spatial, confidence_score, status, explainability_json, report_count, source_diversity,
            dispatch_status, dispatched_agency, dispatch_notes, dispatched_at,
            injuries, threat_state, responders_present, dispute_count, is_lethal_priority, is_regional_cluster,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        incidents_to_add,
    )
    conn.commit()
    if close_at_end:
        conn.close()
supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"[Supabase Warning] Failed to initialize Supabase client: {e}")

def upload_evidence_to_supabase(file_bytes: bytes, filename: str, content_type: str = "image/jpeg") -> Optional[str]:
    """Uploads eyewitness photo proof to Supabase Storage and returns public CDN URL, with graceful fallback."""
    if not supabase:
        return None
    try:
        bucket_name = SUPABASE_STORAGE_BUCKET
        clean_name = filename.replace(" ", "_")
        file_path = f"{int(datetime.utcnow().timestamp())}_{clean_name}"
        
        supabase.storage.from_(bucket_name).upload(
            path=file_path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "true"}
        )
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)
        return public_url
    except Exception as err:
        print(f"[Supabase Storage] Notice: upload deferred to local fallback: {err}")
        return None

def broadcast_realtime_event(event_name: str, payload: dict):
    """Broadcasts a live event to all connected Bugle clients via Supabase Realtime."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        import requests
        url = f"{SUPABASE_URL}/realtime/v1/api/broadcast"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        body = {
            "messages": [
                {
                    "topic": "bugle-alerts",
                    "event": event_name,
                    "payload": payload
                }
            ]
        }
        requests.post(url, headers=headers, json=body, timeout=2.0)
    except Exception as err:
        print(f"[Realtime Broadcast] Notice: {err}")

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode('utf-8')[:72]
    try:
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except Exception:
        return False

def get_connection():
    """Returns a SQLite connection with dict-like row access and WAL mode enabled."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def sync_supabase_user(supabase_id: str, email_or_phone: str, full_name: str = "") -> dict:
    """Syncs or creates a local Bugle profile for a Supabase-authenticated user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (supabase_id,))
    existing = cursor.fetchone()

    now = datetime.utcnow().isoformat()
    if existing:
        user_data = dict(existing)
        conn.close()
        return user_data

    # Determine default role (editor for admin/editor emails, citizen for others)
    is_editor = "editor" in email_or_phone.lower() or "admin" in email_or_phone.lower()
    role = "EDITOR" if is_editor else "CITIZEN"
    display_name = full_name.strip() if full_name else email_or_phone.split("@")[0]
    username_candidate = display_name.lower().replace(" ", "_")

    # Ensure unique username
    cursor.execute("SELECT id FROM users WHERE username = ?", (username_candidate,))
    if cursor.fetchone():
        username_candidate = f"{username_candidate}_{supabase_id[-4:]}"

    cursor.execute("""
        INSERT INTO users (id, username, name, email, phone, password_hash, role, is_verified, trust_score, strike_count, is_quarantined, created_at)
        VALUES (?, ?, ?, ?, ?, '', ?, 1, 0.60, 0, 0, ?)
    """, (supabase_id, username_candidate, display_name, email_or_phone, email_or_phone, role, now))
    conn.commit()

    cursor.execute("SELECT * FROM users WHERE id = ?", (supabase_id,))
    new_user = dict(cursor.fetchone())
    conn.close()
    return new_user

def get_or_create_phone_user(phone: str, full_name: str = "") -> dict:
    """Syncs or creates a citizen stringer profile for a mobile phone verified user."""
    conn = get_connection()
    cursor = conn.cursor()
    clean_phone = phone.strip()
    cursor.execute("SELECT * FROM users WHERE phone = ?", (clean_phone,))
    existing = cursor.fetchone()

    now = datetime.utcnow().isoformat()
    if existing:
        user_data = dict(existing)
        conn.close()
        return user_data

    user_id = f"usr_{uuid.uuid4().hex[:8]}"
    clean_digits = ''.join(c for c in clean_phone if c.isdigit())[-4:] or "press"
    display_name = full_name.strip() if full_name else f"Stringer (+...{clean_digits})"
    username_candidate = f"stringer_{clean_digits}"

    cursor.execute("SELECT id FROM users WHERE username = ?", (username_candidate,))
    if cursor.fetchone():
        username_candidate = f"{username_candidate}_{user_id[-4:]}"

    synthetic_email = f"phone_{clean_phone.replace('+', '').replace(' ', '')}@dailybugle.local"

    cursor.execute("""
        INSERT INTO users (id, username, name, email, phone, password_hash, role, is_verified, trust_score, strike_count, is_quarantined, created_at)
        VALUES (?, ?, ?, ?, ?, '', 'CITIZEN', 1, 0.60, 0, 0, ?)
    """, (user_id, username_candidate, display_name, synthetic_email, clean_phone, now))
    conn.commit()

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    new_user = dict(cursor.fetchone())
    conn.close()
    return new_user
def create_otp_token(identifier: str, purpose: str = "REGISTER", expiry_minutes: int = 5) -> str:
    """Generates a 6-digit verification code and stores it in the database."""
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = (datetime.utcnow() + timedelta(minutes=expiry_minutes)).isoformat()
    
    conn = get_connection()
    cursor = conn.cursor()
    # Invalidate previous unused codes for this identifier
    cursor.execute("""
        UPDATE otp_tokens SET is_used = 1 
        WHERE identifier = ? AND purpose = ? AND is_used = 0
    """, (identifier.strip().lower(), purpose))
    
    cursor.execute("""
        INSERT INTO otp_tokens (identifier, otp_code, purpose, expires_at, is_used)
        VALUES (?, ?, ?, ?, 0)
    """, (identifier.strip().lower(), otp_code, purpose, expires_at))
    conn.commit()
    conn.close()
    
    # Development log to terminal (simulates SMS/Email gateway dispatch)
    print(f"\n=======================================================")
    print(f" [THE DAILY BUGLE DISPATCH - SECURE ACCESS TOKEN]")
    print(f" Target: {identifier} | Purpose: {purpose}")
    print(f" Verification Code: >>> {otp_code} <<< (Valid for {expiry_minutes} mins)")
    print(f"=======================================================\n")
    return otp_code

def verify_otp_token(identifier: str, code: str, purpose: str = "REGISTER") -> bool:
    """Checks validity and expiration of the entered token."""
    now_iso = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM otp_tokens
        WHERE identifier = ? AND otp_code = ? AND purpose = ? AND is_used = 0 AND expires_at > ?
        ORDER BY id DESC LIMIT 1
    """, (identifier.strip().lower(), code.strip(), purpose, now_iso))
    row = cursor.fetchone()
    if row:
        token_id = row["id"]
        cursor.execute("UPDATE otp_tokens SET is_used = 1 WHERE id = ?", (token_id,))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def init_db():
    """Initializes tables, creates indexes, and seeds users/incidents."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Users Table with Contact Verification & Roles
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        email TEXT UNIQUE,
        phone TEXT,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'CITIZEN', -- 'CITIZEN' or 'EDITOR'
        is_verified INTEGER DEFAULT 0,
        trust_score REAL DEFAULT 0.50,
        strike_count INTEGER DEFAULT 0,
        is_quarantined INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    # 2. OTP Verification Token Store
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS otp_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        identifier TEXT NOT NULL,
        otp_code TEXT NOT NULL,
        purpose TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        is_used INTEGER DEFAULT 0
    );
    """)

    # 3. Incidents Table with Comprehensive Editorial Article Support
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        full_article TEXT NOT NULL,
        primary_image TEXT DEFAULT '',
        category TEXT NOT NULL,
        latitude REAL DEFAULT 0.0,
        longitude REAL DEFAULT 0.0,
        is_spatial INTEGER DEFAULT 1,
        confidence_score INTEGER DEFAULT 50,
        status TEXT DEFAULT 'REVIEW', -- 'VERIFIED', 'COMMUNITY', 'REVIEW', 'BUSTED'
        explainability_json TEXT NOT NULL,
        report_count INTEGER DEFAULT 1,
        source_diversity INTEGER DEFAULT 1,
        dispatch_status TEXT DEFAULT 'PENDING', -- 'PENDING', 'DISPATCHED', 'UNITS_EN_ROUTE', 'ON_SCENE', 'RESOLVED'
        dispatched_agency TEXT DEFAULT NULL,    -- 'POLICE', 'FIRE', 'AMBULANCE', 'CIVIC'
        dispatch_notes TEXT DEFAULT NULL,
        dispatched_at TEXT DEFAULT NULL,
        injuries TEXT DEFAULT 'NONE',           -- 'NONE', 'SUSPECTED', 'CONFIRMED'
        threat_state TEXT DEFAULT 'ACTIVE',     -- 'ACTIVE', 'CONTAINED', 'CLEARED'
        responders_present TEXT DEFAULT 'NONE', -- 'NONE', 'POLICE', 'FIRE', 'AMBULANCE'
        dispute_count INTEGER DEFAULT 0,
        is_lethal_priority INTEGER DEFAULT 0,
        is_regional_cluster INTEGER DEFAULT 0,
        credibility_matrix_json TEXT DEFAULT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 4. Citizen Eyewitness Reports Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        incident_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        description TEXT NOT NULL,
        latitude REAL DEFAULT 0.0,
        longitude REAL DEFAULT 0.0,
        is_spatial INTEGER DEFAULT 1,
        image_url TEXT DEFAULT '',
        injuries TEXT DEFAULT 'NONE',
        threat_state TEXT DEFAULT 'ACTIVE',
        responders_present TEXT DEFAULT 'NONE',
        client_ip TEXT DEFAULT '127.0.0.1',
        device_hash TEXT DEFAULT '',
        image_hash TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE
    );
    """)

    # 5. Cryptographic Image Provenance Hashes Store
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS image_hashes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_hash TEXT UNIQUE NOT NULL,
        incident_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE
    );
    """)

    # Performance Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_coords ON incidents(latitude, longitude);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_incident ON reports(incident_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_otp_lookup ON otp_tokens(identifier, otp_code, purpose);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_image_hashes_hash ON image_hashes(image_hash);")

    now = datetime.utcnow().isoformat()

    # Seed Default Verified Accounts if missing
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO users (id, username, name, email, phone, password_hash, role, is_verified, trust_score, strike_count, is_quarantined, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "usr_editor", "editor", "J. Jonah Jameson", "editor@dailybugle.com", "+919876543210",
            hash_password("admin123"), "EDITOR", 1, 1.0, 0, 0, now
        ))

        cursor.execute("""
        INSERT INTO users (id, username, name, email, phone, password_hash, role, is_verified, trust_score, strike_count, is_quarantined, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "usr_peter", "peter", "Peter Parker", "peter@dailybugle.com", "+919876543211",
            hash_password("dailybugle123"), "CITIZEN", 1, 0.95, 0, 0, now
        ))

        cursor.execute("""
        INSERT INTO users (id, username, name, email, phone, password_hash, role, is_verified, trust_score, strike_count, is_quarantined, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "usr_dispatcher", "dispatcher", "Capt. George Stacy", "dispatch@police.gov.in", "+919876543299",
            hash_password("dispatch123"), "DISPATCHER", 1, 1.0, 0, 0, now
        ))

    # Seed Comprehensive Starter Articles if missing
    cursor.execute("SELECT COUNT(*) FROM incidents")
    if cursor.fetchone()[0] == 0:
        exp_fire = json.dumps([
            {"label": "Independent eyewitness accounts", "value": "+24"},
            {"label": "Direct photo evidence matches scene", "value": "+18"},
            {"label": "Geographic cluster tight within 120m", "value": "+15"}
        ])
        article_fire = (
            "Emergency response units arrived at KIIT Square at approximately 10:45 AM following reports "
            "of a sudden explosion at the secondary power distribution unit. Heavy smoke billowed across the main intersection, "
            "impacting traffic toward Nandankanan Road.\n\n"
            "Fire brigade teams managed to contain the blaze within 30 minutes, preventing electrical fires from spreading to adjacent commercial blocks. "
            "Municipal power grid authorities confirmed maintenance teams are isolating lines. Commuters are advised to divert via Infocity Avenue."
        )
        cursor.execute("""
        INSERT INTO incidents (title, summary, full_article, primary_image, category, latitude, longitude, is_spatial, confidence_score, status, explainability_json, report_count, source_diversity, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "Electrical Substation Fire at KIIT Square",
            "Transformer burst near KIIT Square causing power outages; emergency crews en route.",
            article_fire, "", "Fire", 20.3533, 85.8189, 1, 82, "VERIFIED", exp_fire, 7, 5, now, now
        ))
        inc_fire_id = cursor.lastrowid
        cursor.execute("""
        INSERT INTO reports (user_id, incident_id, category, description, latitude, longitude, is_spatial, image_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("usr_peter", inc_fire_id, "Fire", "Huge black smoke and sparks coming out of transformer.", 20.3533, 85.8189, 1, "", now))

        exp_roadblock = json.dumps([
            {"label": "3 commuter reports filed", "value": "+18"},
            {"label": "Matching coordinates along NH-16", "value": "+14"}
        ])
        article_roadblock = (
            "Following persistent overnight showers, substantial water accumulation coupled with an uprooted banyan tree "
            "has obstructed two outbound lanes on the NH-16 service corridor near Patia.\n\n"
            "Civic cleanup machinery is currently on-site clearing timber debris. Traffic police have instituted temporary single-lane routing. "
            "Expected clearance time is approximately 2 hours."
        )
        cursor.execute("""
        INSERT INTO incidents (title, summary, full_article, primary_image, category, latitude, longitude, is_spatial, confidence_score, status, explainability_json, report_count, source_diversity, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "Waterlogging & Fallen Tree on NH-16 Service Road",
            "Severe waterlogging and a large tree branch blocking two lanes near Patia.",
            article_roadblock, "", "Obstruction", 20.3588, 85.8201, 1, 46, "COMMUNITY", exp_roadblock, 3, 3, now, now
        ))

        exp_busted = json.dumps([
            {"label": "Recycled earthquake stock image detected", "value": "-35"},
            {"label": "Zero municipal emergency call correlation", "value": "-25"}
        ])
        article_busted = (
            "Circulating WhatsApp claims depicting cracked structural pillars along the Rasulgarh flyover have been evaluated and debunked. "
            "Our automated visual provenance verification identified the circulating graphic as an archival photo from a 2018 infrastructure incident elsewhere.\n\n"
            "National Highways Authority of India (NHAI) structural inspectors conducted a physical survey this morning and confirmed zero structural flaws."
        )
        cursor.execute("""
        INSERT INTO incidents (title, summary, full_article, primary_image, category, latitude, longitude, is_spatial, confidence_score, status, explainability_json, report_count, source_diversity, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "Viral Rumor: False Flyover Crack Claim",
            "Social media rumor claiming structural collapse on Rasulgarh flyover debunked by NHAI engineers.",
            article_busted, "", "Disaster", 20.3012, 85.8566, 1, 10, "BUSTED", exp_busted, 8, 1, now, now
        ))

    conn.commit()
    conn.close()

    # Automatically apply any pending migrations
    migrate_schema()

    # Seed batches 6-11 if needed
    try:
        seed_batch_incidents_6_to_9()
        seed_batch_incidents_10_and_11()
    except Exception as e:
        print(f"[DB Notice] Seed batches notice: {e}")

def migrate_schema():
    """Applies non-destructive schema migrations to existing databases."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(incidents);")
    columns = [row["name"] for row in cursor.fetchall()]
    
    if "dispatch_status" not in columns:
        cursor.execute("ALTER TABLE incidents ADD COLUMN dispatch_status TEXT DEFAULT 'PENDING';")
    if "dispatched_agency" not in columns:
        cursor.execute("ALTER TABLE incidents ADD COLUMN dispatched_agency TEXT DEFAULT NULL;")
    if "dispatch_notes" not in columns:
        cursor.execute("ALTER TABLE incidents ADD COLUMN dispatch_notes TEXT DEFAULT NULL;")
    if "dispatched_at" not in columns:
        cursor.execute("ALTER TABLE incidents ADD COLUMN dispatched_at TEXT DEFAULT NULL;")
    if "injuries" not in columns:
        cursor.execute("ALTER TABLE incidents ADD COLUMN injuries TEXT DEFAULT 'NONE';")
    if "threat_state" not in columns:
        cursor.execute("ALTER TABLE incidents ADD COLUMN threat_state TEXT DEFAULT 'ACTIVE';")
    if "responders_present" not in columns:
        cursor.execute("ALTER TABLE incidents ADD COLUMN responders_present TEXT DEFAULT 'NONE';")
    if "dispute_count" not in columns:
        cursor.execute("ALTER TABLE incidents ADD COLUMN dispute_count INTEGER DEFAULT 0;")
    if "is_lethal_priority" not in columns:
        cursor.execute("ALTER TABLE incidents ADD COLUMN is_lethal_priority INTEGER DEFAULT 0;")
    if "is_regional_cluster" not in columns:
        cursor.execute("ALTER TABLE incidents ADD COLUMN is_regional_cluster INTEGER DEFAULT 0;")
    if "credibility_matrix_json" not in columns:
        cursor.execute("ALTER TABLE incidents ADD COLUMN credibility_matrix_json TEXT DEFAULT NULL;")

    cursor.execute("PRAGMA table_info(reports);")
    report_columns = [row["name"] for row in cursor.fetchall()]
    if "injuries" not in report_columns:
        cursor.execute("ALTER TABLE reports ADD COLUMN injuries TEXT DEFAULT 'NONE';")
    if "threat_state" not in report_columns:
        cursor.execute("ALTER TABLE reports ADD COLUMN threat_state TEXT DEFAULT 'ACTIVE';")
    if "responders_present" not in report_columns:
        cursor.execute("ALTER TABLE reports ADD COLUMN responders_present TEXT DEFAULT 'NONE';")
    if "client_ip" not in report_columns:
        cursor.execute("ALTER TABLE reports ADD COLUMN client_ip TEXT DEFAULT '127.0.0.1';")
    if "device_hash" not in report_columns:
        cursor.execute("ALTER TABLE reports ADD COLUMN device_hash TEXT DEFAULT '';")
    if "image_hash" not in report_columns:
        cursor.execute("ALTER TABLE reports ADD COLUMN image_hash TEXT DEFAULT '';")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS disputes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        note TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS image_hashes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_hash TEXT UNIQUE NOT NULL,
        incident_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_image_hashes_hash ON image_hashes(image_hash);")

    conn.commit()
    conn.close()

def record_image_hash(image_hash: str, incident_id: int) -> bool:
    """Stores an image hash linked to an incident for perceptual provenance auditing."""
    if not image_hash:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO image_hashes (image_hash, incident_id, created_at)
            VALUES (?, ?, ?)
        """, (image_hash, incident_id, now))
        conn.commit()
        conn.close()
        return True
    except Exception as err:
        print(f"[Image Hash Notice] Could not record hash: {err}")
        conn.close()
        return False

def find_image_hash(image_hash: str) -> Optional[dict]:
    """Finds an existing identical or near-identical image hash in prior reports."""
    if not image_hash:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ih.*, i.title, i.status, i.created_at as incident_created_at
        FROM image_hashes ih
        JOIN incidents i ON ih.incident_id = i.id
        WHERE ih.image_hash = ?
        ORDER BY ih.id ASC LIMIT 1
    """, (image_hash,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_incident_disputes(incident_id: int) -> list:
    """Returns all citizen on-scene dispute observations for an incident."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.*, u.name as disputer_name, u.role as disputer_role, u.trust_score as disputer_trust
        FROM disputes d
        LEFT JOIN users u ON d.user_id = u.id
        WHERE d.incident_id = ?
        ORDER BY d.created_at DESC
    """, (incident_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def update_incident_dispatch(incident_id: int, agency: str, status: str, notes: str = "") -> dict:
    """Updates emergency dispatch lifecycle for verified incidents."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
        UPDATE incidents
        SET dispatch_status = ?, dispatched_agency = ?, dispatch_notes = ?, dispatched_at = ?, updated_at = ?
        WHERE id = ?
    """, (status, agency, notes, now, now, incident_id))
    conn.commit()
    cursor.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    updated = cursor.fetchone()
    conn.close()
    return dict(updated) if updated else {}

def seed_batch_incidents_10_and_11(conn=None):
    """Seeds realistic incidents 10 and 11 and their initial reports safely."""
    close_at_end = False
    if conn is None:
        conn = get_connection()
        close_at_end = True
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # 1. Incidents Definitions
    new_incidents = [
        # Incident 10: Under Audit Queue (UNVERIFIED)
        (
            10,
            "Subsurface Cable Sparking Near Sailashree Vihar",
            "Single citizen report of sparking and popping noises from utility junction; awaiting second corroborator.",
            "A lone eyewitness transmission logged claims recurring sparks and popping noises emitting from a utility junction box along Sailashree Vihar Main Road. The signal remains uncorroborated and is held in the Under Audit Queue.",
            "",
            "Civic",
            20.3284,
            85.8071,
            1,
            34,
            "UNVERIFIED",
            json.dumps([
                {"label": "Initial eyewitness submission", "value": "+25"},
                {"label": "Awaiting independent corroboration", "value": "-15"},
                {"label": "Geotag matched to utility corridor", "value": "+10"},
            ]),
            1,
            1,
            "PENDING",
            "CIVIC",
            "Pending second independent verification before dispatching field crews.",
            None,
            "NONE",
            "ACTIVE",
            "NONE",
            0,
            0,
            0,
            now,
            now,
        ),
        # Incident 11: Police Assault Queue (VERIFIED / DISPATCHED)
        (
            11,
            "Violent Market Altercation & Public Disturbance at Bapuji Nagar",
            "Violent confrontation involving blunt objects outside market stalls; PCR 112 units actively dispatched.",
            "Rapid Response Police PCR units were dispatched to Bapuji Nagar market following urgent eyewitness transmissions reporting a violent group altercation spilling onto the roadway. Two individuals sustained minor injuries; police units are securing the lane.",
            "",
            "Assault",
            20.2614,
            85.8331,
            1,
            86,
            "VERIFIED",
            json.dumps([
                {"label": "Corroborated by 3 independent reports", "value": "+22"},
                {"label": "Anti-Sybil Subnet Diversity: 3 networks", "value": "+18"},
                {"label": "Confirmed casualty threat priority", "value": "+15"},
                {"label": "Police 112 Units Dispatched", "value": "+15"},
            ]),
            3,
            3,
            "DISPATCHED",
            "POLICE",
            "PCR Van 12 and Capital Station patrol units dispatched to Bapuji Nagar square.",
            now,
            "CONFIRMED",
            "ACTIVE",
            "POLICE",
            0,
            0,
            0,
            now,
            now,
        ),
    ]
    
    cursor.executemany(
        """
        INSERT OR REPLACE INTO incidents (
            id, title, summary, full_article, primary_image, category, latitude, longitude,
            is_spatial, confidence_score, status, explainability_json, report_count, source_diversity,
            dispatch_status, dispatched_agency, dispatch_notes, dispatched_at,
            injuries, threat_state, responders_present, dispute_count, is_lethal_priority, is_regional_cluster,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        new_incidents,
    )

    cursor.execute("""
        INSERT OR IGNORE INTO users (id, username, name, email, phone, password_hash, role, is_verified, trust_score, strike_count, is_quarantined, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("usr_stringer1", "stringer_patia", "Ravi Mohanty", "stringer@dailybugle.com", "+919876543212", hash_password("citizen123"), "CITIZEN", 1, 0.75, 0, 0, now))

    # 2. Corroborating Reports Definitions
    new_reports = [
        # Report for Incident 10 (Under Audit)
        (
            "usr_stringer1",
            10,
            "Civic",
            "Hearing sharp electrical cracking sounds and seeing intermittent blue sparks coming from the roadside trench near the Sai Temple turn.",
            20.3284,
            85.8071,
            1,
            "",
            "NONE",
            "ACTIVE",
            "NONE",
            "192.168.1.45",
            "ua_stringer_device",
            "",
            now,
        ),
        # Reports for Incident 11 (Police Assault)
        (
            "usr_peter",
            11,
            "Assault",
            "Large group fighting with sticks outside the electronics arcade. Glass bottles thrown onto the road.",
            20.2614,
            85.8331,
            1,
            "",
            "CONFIRMED",
            "ACTIVE",
            "POLICE",
            "10.0.0.12",
            "ua_peter_phone",
            "",
            now,
        ),
        (
            "usr_stringer1",
            11,
            "Assault",
            "Two shop workers injured while trying to pull their merchandise inside. Traffic completely halted on Bapuji Nagar 1st line.",
            20.2616,
            85.8333,
            1,
            "",
            "CONFIRMED",
            "ACTIVE",
            "POLICE",
            "172.16.4.88",
            "ua_stringer_tablet",
            "",
            now,
        ),
        (
            "usr_editor",
            11,
            "Assault",
            "Police siren audible; PCR van turning into the market from the Janpath junction.",
            20.2612,
            85.8329,
            1,
            "",
            "CONFIRMED",
            "ACTIVE",
            "POLICE",
            "127.0.0.1",
            "ua_desk_terminal",
            "",
            now,
        ),
    ]
    
    cursor.executemany(
        """
        INSERT INTO reports (
            user_id, incident_id, category, description, latitude, longitude,
            is_spatial, image_url, injuries, threat_state, responders_present,
            client_ip, device_hash, image_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        new_reports,
)
    conn.commit()
    if close_at_end:
        conn.close()

    # 3. Compute Credibility Matrices
    try:
        import trust_engine

        trust_engine.compute_credibility_matrix(10)
        trust_engine.compute_credibility_matrix(11)
    except Exception as e:
        pass

if __name__ == "__main__":
    init_db()
    print("Database schema successfully configured with OTP tokens, article structures, and dispatch pipelines.")