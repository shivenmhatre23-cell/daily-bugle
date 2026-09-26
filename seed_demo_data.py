"""
=============================================================================
THE DAILY BUGLE - 1-CLICK HACKATHON DEMO SEEDER
=============================================================================
Populates the database with realistic, high-impact demonstration data for
judges, showcasing:
1. Active Emergency Dispatches (Police 112, Fire 101, Ambulance 108)
2. High-confidence verified incidents with AI explainability and corroboration
3. Community alerts with on-scene eyewitness logs
4. Debunked viral misinformation in the Busted Graveyard
5. Pre-configured demo user accounts with varying clearance levels
"""

import os
import sqlite3
import json
from datetime import datetime, timedelta
import sys
import bcrypt

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bugle.db")

def hash_pwd(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8')[:72], bcrypt.gensalt()).decode('utf-8')

def seed():
    print("\n[DAILY BUGLE] Seeding authoritative hackathon demo data...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Clear existing records
    cursor.execute("DELETE FROM reports;")
    cursor.execute("DELETE FROM incidents;")
    cursor.execute("DELETE FROM users;")
    cursor.execute("DELETE FROM otp_tokens;")
    cursor.execute("DELETE FROM disputes;")
    cursor.execute("DELETE FROM image_hashes;")

    now = datetime.now()
    t_now = now.isoformat()
    t_minus_10m = (now - timedelta(minutes=10)).isoformat()
    t_minus_20m = (now - timedelta(minutes=20)).isoformat()
    t_minus_25m = (now - timedelta(minutes=25)).isoformat()
    t_minus_35m = (now - timedelta(minutes=35)).isoformat()
    t_minus_45m = (now - timedelta(minutes=45)).isoformat()
    t_minus_2h = (now - timedelta(hours=2)).isoformat()

    # 1. Seed Authorized Users
    users = [
        ("usr_editor", "editor", "J. Jonah Jameson", "editor@dailybugle.com", "+919876543210", hash_pwd("admin123"), "EDITOR", 1, 1.0, 0, 0, t_minus_2h),
        ("usr_peter", "peter", "Peter Parker", "peter@dailybugle.com", "+919876543211", hash_pwd("dailybugle123"), "CITIZEN", 1, 0.95, 0, 0, t_minus_2h),
        ("usr_dispatcher", "dispatcher", "Capt. George Stacy", "dispatch@police.gov.in", "+919876543299", hash_pwd("dispatch123"), "DISPATCHER", 1, 1.0, 0, 0, t_minus_2h),
        ("usr_robbie", "robbie", "Robbie Robertson", "robbie@dailybugle.com", "+919876543212", hash_pwd("admin123"), "EDITOR", 1, 0.92, 0, 0, t_minus_2h),
        ("usr_stringer1", "stringer_patia", "Ravi Mohapatra", "ravi@patia.in", "+919876543213", hash_pwd("citizen123"), "CITIZEN", 1, 0.75, 0, 0, t_minus_2h),
        ("usr_fabricator", "tabloid_troll", "Spam Account", "spammer@rumor.net", "+919876543214", hash_pwd("badactor123"), "CITIZEN", 0, 0.05, 3, 1, t_minus_2h)
    ]

    cursor.executemany("""
        INSERT INTO users (id, username, name, email, phone, password_hash, role, is_verified, trust_score, strike_count, is_quarantined, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, users)
    print(" -> Seeded 6 demo user accounts (Editor, Dispatcher, Pulitzer Correspondent, Field Stringers, Quarantined Troll)")

    # 2. Seed Incidents & Actionable Dispatches

    # INCIDENT 1: 4-Alarm Chemical Fire (Fire 101 Dispatched)
    fire_explain = json.dumps([
        {"label": "Corroborated by 4 citizen reports", "value": "+20"},
        {"label": "Source diversity: 3 independent reporters", "value": "+15"},
        {"label": "Geospatial proximity verified within 120m & 25 mins", "value": "+15"},
        {"label": "Vision Audit: Thermal signature and dense smoke plume authentic", "value": "+15"},
        {"label": "Gemini Threat Extraction: Chemical substation hazard confirmed", "value": "+12"}
    ])
    fire_article = (
        "Four municipal fire brigades and a specialized HAZMAT chemical foam unit responded to KIIT Square at 10:15 AM "
        "following multiple eyewitness transmissions corroborating a secondary transformer explosion.\n\n"
        "Dense petroleum-laced smoke temporarily choked visibility along Nandankanan Road. Fire Chief S. Patnaik confirmed "
        "the blaze was successfully contained before reaching commercial storefronts. Power grid technicians are isolating the 33kV circuit. "
        "Commuters are urged to bypass KIIT Square via Infocity Avenue until cleanup operations conclude."
    )
    cursor.execute("""
        INSERT INTO incidents (
            id, title, summary, full_article, primary_image, category, latitude, longitude,
            is_spatial, confidence_score, status, explainability_json, report_count, source_diversity,
            dispatch_status, dispatched_agency, dispatch_notes, dispatched_at,
            injuries, threat_state, responders_present, dispute_count, created_at, updated_at
        ) VALUES (
            1, '4-Alarm Electrical Substation Fire at KIIT Square',
            'Transformer rupture sparking commercial hazard; 4 fire tenders deployed on-scene.',
            ?, '', 'Fire', 20.3533, 85.8189, 1, 94, 'VERIFIED', ?, 4, 3,
            'ON_SCENE', 'FIRE', '4 units deployed with chemical foam tanks; containment perimeter established.',
            ?, 'NONE', 'ACTIVE', 'FIRE', 0, ?, ?
        )
    """, (fire_article, fire_explain, t_minus_25m, t_minus_45m, t_minus_10m))

    # Reports for Incident 1
    cursor.execute("""
        INSERT INTO reports (user_id, incident_id, category, description, latitude, longitude, is_spatial, image_url, created_at)
        VALUES 
        ('usr_peter', 1, 'Fire', 'Explosion heard from substation behind commercial complex. Heavy black smoke spreading fast.', 20.3533, 85.8189, 1, '', ?),
        ('usr_stringer1', 1, 'Fire', 'Flames visible at top of transformer. Heat wave felt across 4-lane intersection.', 20.3535, 85.8191, 1, '', ?),
        ('usr_editor', 1, 'Fire', 'Police barricading north quadrant. Fire tender #4 actively spraying chemical foam.', 20.3531, 85.8187, 1, '', ?)
    """, (t_minus_45m, t_minus_35m, t_minus_20m))

    # INCIDENT 2: Public Altercation / Crowd Hazard (Police 112 Dispatched)
    police_explain = json.dumps([
        {"label": "Corroborated by 3 citizen reports", "value": "+18"},
        {"label": "Source diversity: 3 independent reporters", "value": "+14"},
        {"label": "High-risk escalation detection", "value": "+15"},
        {"label": "Proximity to high-density transit hub", "value": "+10"}
    ])
    police_article = (
        "Police PCR vans have arrived at the Master Canteen Railway entrance following urgent transmissions regarding "
        "a physical altercation that spilled into the pedestrian thoroughfare.\n\n"
        "Security personnel secured the central ticket concourse and dispersed unlawful assemblies. Traffic flow has normalized."
    )
    cursor.execute("""
        INSERT INTO incidents (
            id, title, summary, full_article, primary_image, category, latitude, longitude,
            is_spatial, confidence_score, status, explainability_json, report_count, source_diversity,
            dispatch_status, dispatched_agency, dispatch_notes, dispatched_at,
            injuries, threat_state, responders_present, dispute_count, created_at, updated_at
        ) VALUES (
            2, 'Public Disturbance & Commuter Bottleneck at Railway Plaza',
            'Severe congestion and altercation near Platform 1 concourse; PCR units en route.',
            ?, '', 'Assault', 20.2667, 85.8436, 1, 84, 'VERIFIED', ?, 3, 3,
            'UNITS_EN_ROUTE', 'POLICE', 'PCR van 04 and quick reaction team dispatched from Capital Station.',
            ?, 'SUSPECTED', 'ACTIVE', 'POLICE', 0, ?, ?
        )
    """, (police_article, police_explain, t_minus_10m, t_minus_25m, t_now))

    cursor.execute("""
        INSERT INTO reports (user_id, incident_id, category, description, latitude, longitude, is_spatial, image_url, injuries, threat_state, responders_present, created_at)
        VALUES 
        ('usr_stringer1', 2, 'Assault', 'Aggressive dispute blocking the main passenger exit gate.', 20.2667, 85.8436, 1, '', 'SUSPECTED', 'ACTIVE', 'POLICE', ?)
    """, (t_minus_25m,))

    # INCIDENT 3: Waterlogging & Fallen Banyan Tree (Ambulance / Civic Alert)
    road_explain = json.dumps([
        {"label": "Corroborated by 2 commuter reports", "value": "+12"},
        {"label": "Matching coordinates along NH-16 corridor", "value": "+14"},
        {"label": "Awaiting municipality heavy crane confirmation", "value": "-5"}
    ])
    road_article = (
        "Substantial water accumulation coupled with an uprooted banyan tree branch has obstructed two outbound lanes "
        "on the NH-16 service road near Patia.\n\n"
        "Municipal emergency response teams are operating chainsaws on-site to restore traffic."
    )
    cursor.execute("""
        INSERT INTO incidents (
            id, title, summary, full_article, primary_image, category, latitude, longitude,
            is_spatial, confidence_score, status, explainability_json, report_count, source_diversity,
            dispatch_status, dispatched_agency, dispatch_notes, dispatched_at,
            injuries, threat_state, responders_present, dispute_count, created_at, updated_at
        ) VALUES (
            3, 'Waterlogging & Fallen Tree on NH-16 Service Road',
            'Fallen tree branch and waterlogging blocking two lanes; traffic diverting to single file.',
            ?, '', 'Obstruction', 20.3588, 85.8201, 1, 64, 'COMMUNITY', ?, 2, 2,
            'DISPATCHED', 'AMBULANCE', 'Emergency medical vehicle standby alerted due to road bottleneck.',
            ?, 'NONE', 'CONTAINED', 'NONE', 0, ?, ?
        )
    """, (road_article, road_explain, t_minus_10m, t_minus_45m, t_now))

    # INCIDENT 4: Busted Viral Hoax (Misinformation Graveyard)
    hoax_explain = json.dumps([
        {"label": "Vision Audit: Recycled 2017 CGI movie still detected", "value": "-40"},
        {"label": "Zero municipal radar or ATC confirmation", "value": "-25"},
        {"label": "Submitted by flagged user with history of fake claims", "value": "-20"}
    ])
    hoax_article = (
        "Viral claims circulating on messaging groups alleging an 'Unidentified Extraterrestrial Aircraft' hovering "
        "over the Odisha State Secretariat dome have been conclusively debunked.\n\n"
        "Our forensic vision cascade matched the circulating graphic to a VFX render originally published in 2017. "
        "Radar controllers at Biju Patnaik International Airport confirmed standard airspace activity. The submitter account has received a strike."
    )
    cursor.execute("""
        INSERT INTO incidents (
            id, title, summary, full_article, primary_image, category, latitude, longitude,
            is_spatial, confidence_score, status, explainability_json, report_count, source_diversity,
            dispatch_status, dispatched_agency, dispatch_notes, dispatched_at,
            injuries, threat_state, responders_present, dispute_count, created_at, updated_at
        ) VALUES (
            4, 'Viral Hoax: Fabricated Aerial Sighting Over Secretariat',
            'Debunked CGI imagery falsely claiming unidentified craft over State Secretariat; zero ATC radar detection.',
            ?, '', 'Disaster', 20.2961, 85.8245, 1, 10, 'BUSTED', ?, 1, 1,
            'RESOLVED', 'CIVIC', 'Debunked misinformation hoax. No municipal emergency response needed.',
            ?, 'NONE', 'CLEARED', 'NONE', 0, ?, ?
        )
    """, (hoax_article, hoax_explain, t_minus_2h, t_minus_2h, t_minus_10m))

    cursor.execute("""
        INSERT INTO reports (user_id, incident_id, category, description, latitude, longitude, is_spatial, image_url, injuries, threat_state, responders_present, created_at)
        VALUES ('usr_fabricator', 4, 'Disaster', 'Giant flying saucer floating over Secretariat roof! Everyone look outside!', 20.2961, 85.8245, 1, '', 'NONE', 'CLEARED', 'NONE', ?)
    """, (t_minus_2h,))

    # INCIDENT 5: Fresh Signal Under Review (UNVERIFIED)
    review_explain = json.dumps([
        {"label": "Initial eyewitness filing", "value": "+35"},
        {"label": "Awaiting second independent corroborator", "value": "-10"},
        {"label": "Geotag acquired near Infocity sewer line", "value": "+10"}
    ])
    cursor.execute("""
        INSERT INTO incidents (
            id, title, summary, full_article, primary_image, category, latitude, longitude,
            is_spatial, confidence_score, status, explainability_json, report_count, source_diversity,
            dispatch_status, dispatched_agency, dispatch_notes, dispatched_at,
            injuries, threat_state, responders_present, dispute_count, created_at, updated_at
        ) VALUES (
            5, 'Unusual Chemical Odor Near Infocity Drainage Line',
            'Eyewitness reports pungent sulfur/gas smell near tech corridor storm drain; monitoring underway.',
            'Initial citizen filing received regarding strong sulfur odor along Infocity drainage line. Municipal environmental sensors pending review.',
            '', 'Civic', 20.3541, 85.8142, 1, 38, 'UNVERIFIED', ?, 1, 1,
            'PENDING', 'CIVIC', 'Pending second independent verification before dispatching field crews.',
            NULL, 'NONE', 'ACTIVE', 'NONE', 0, ?, ?
        )
    """, (review_explain, t_now, t_now))

    conn.commit()
    conn.close()
    print(" -> Seeded 5 diverse incidents: Fire 101, Police 112, Civic/Ambulance, Busted Hoax, and Review Queue.")

    # Compute and persist 4-vector Credibility Matrix & Ground Truth Attestation for all seeded incidents
    try:
        import trust_engine
        for inc_id in [1, 2, 3, 4, 5]:
            trust_engine.compute_credibility_matrix(inc_id)
        print(" -> Computed 4-Vector Evidence Integrity Matrix and Ground Truth Attestation for all demo incidents.")
    except Exception as e:
        print(f" -> Matrix computation notice: {e}")

    print("[DAILY BUGLE] Demo data seeding completed successfully! Launch server with: py -3.13 main.py\n")

if __name__ == "__main__":
    seed()

