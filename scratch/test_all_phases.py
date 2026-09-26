"""
Automated Test Suite for Daily Bugle All-Phases Hackathon Upgrades
12 Comprehensive Integration Tests covering RBAC, Clustering, Freshness, Disputes, and Rate Limits.
"""
import os
import sys
import json
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
import database
import trust_engine
import seed_demo_data

client = TestClient(main.app)

def test_suite():
    # Seed fresh, authoritative demo records before running test assertions
    seed_demo_data.seed()

    print("\n=======================================================")
    print(" [THE DAILY BUGLE - COMPREHENSIVE 17-PHASE TEST SUITE]")
    print("=======================================================\n")
    
    passed = 0
    total = 17

    # 1. Check Incidents Feed & Dispatch Columns
    print("Test 1: Public Incidents Feed & Dispatch Metadata")
    res = client.get("/api/incidents?view=wire")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    incidents = res.json()
    assert len(incidents) >= 3, f"Expected verified/community incidents, got {len(incidents)}"
    sample = incidents[0]
    assert "dispatch_status" in sample, "Missing dispatch_status column in incident"
    assert "dispatched_agency" in sample, "Missing dispatched_agency column in incident"
    assert "injuries" in sample, "Missing injuries column in incident"
    print(f" -> PASSED: Fetched {len(incidents)} verified/community incidents with full dispatch and triage schemas.")
    passed += 1

    # 2. Check Single Incident Deep Dive & Structured Metrics
    print("\nTest 2: Single Incident Retrieval & Structured Metrics")
    res = client.get("/api/incidents/1")
    assert res.status_code == 200
    inc1 = res.json()
    assert inc1["id"] == 1
    assert "reports" in inc1
    assert "disputes" in inc1
    assert "threat_state" in inc1
    print(f" -> PASSED: Incident #1 retrieved with structured triage (Threat: {inc1['threat_state']}, Injuries: {inc1.get('injuries')}, Disputes: {len(inc1['disputes'])}).")
    passed += 1

    # 3. Test RBAC Dispatch Protection (403 for Citizen, 200 for Dispatcher)
    print("\nTest 3: RBAC Dispatch Protection (Citizen blocked, Dispatcher authorized)")
    # 3a. Citizen attempt (must fail with 403 Forbidden)
    peter_login = client.post("/api/auth/login", data={"username": "peter", "password": "dailybugle123"})
    assert peter_login.status_code == 200
    peter_cookies = peter_login.cookies

    unauth_disp = client.post(
        "/api/incidents/1/dispatch",
        data={"agency": "FIRE", "status": "ON_SCENE", "notes": "Unauthorized citizen trigger"},
        cookies=peter_cookies
    )
    assert unauth_disp.status_code == 403, f"Expected 403 Forbidden for Citizen, got {unauth_disp.status_code}"
    print(" -> PASSED (Part A): Citizen account blocked from emergency dispatch with 403 Forbidden.")

    # 3b. Dispatcher attempt (must succeed with 200 OK)
    disp_login = client.post("/api/auth/login", data={"username": "dispatcher", "password": "dispatch123"})
    assert disp_login.status_code == 200
    disp_cookies = disp_login.cookies

    auth_disp = client.post(
        "/api/incidents/1/dispatch",
        data={"agency": "FIRE", "status": "ON_SCENE", "notes": "Authorized units on scene."},
        cookies=disp_cookies
    )
    assert auth_disp.status_code == 200, f"Expected 200 OK for Dispatcher, got {auth_disp.status_code}"
    assert auth_disp.json()["status"] == "success"
    print(" -> PASSED (Part B): Emergency Dispatcher successfully transitioned incident to ON_SCENE.")
    passed += 1

    # 4. Check Printable SITREP Bulletin Route
    print("\nTest 4: Printable SITREP Bulletin Generation")
    bulletin_res = client.get("/incident/1/bulletin")
    assert bulletin_res.status_code == 200
    assert "Security Advisory SITREP" in bulletin_res.text
    assert "bulletin-paper" in bulletin_res.text
    print(" -> PASSED: SITREP Bulletin serves cleanly with print-optimized styling.")
    passed += 1

    # 5. Check Emergency Dispatch Console UI Access Restriction
    print("\nTest 5: Dispatch Console UI Access Restriction")
    # Citizen trying to access /dispatch -> redirected
    citizen_ui = client.get("/dispatch", cookies=peter_cookies, follow_redirects=False)
    assert citizen_ui.status_code == 302, f"Expected 302 redirect for Citizen, got {citizen_ui.status_code}"

    # Dispatcher accessing /dispatch -> 200 OK
    disp_ui = client.get("/dispatch", cookies=disp_cookies)
    assert disp_ui.status_code == 200
    assert "Security & Emergency Services Dispatch" in disp_ui.text
    print(" -> PASSED: Dispatch UI correctly gates access to authorized personnel.")
    passed += 1

    # 6. Test In-Place Eyewitness Corroboration
    print("\nTest 6: In-Place Eyewitness Corroboration API")
    initial_inc3 = client.get("/api/incidents/3").json()
    init_score = initial_inc3["confidence_score"]
    init_count = initial_inc3["report_count"]

    corr_res = client.post(
        "/api/incidents/3/corroborate",
        data={"description": "Can confirm tree branch is being cut right now, lane opening soon."},
        cookies=peter_cookies
    )
    assert corr_res.status_code == 200
    corr_data = corr_res.json()
    assert corr_data["status"] == "success"
    assert corr_data["incident"]["report_count"] == init_count + 1
    print(f" -> PASSED: Corroboration updated report count ({init_count} -> {corr_data['incident']['report_count']}) and elevated status.")
    passed += 1

    # 7. Test Gemini Multimodal Vision Authenticator
    print("\nTest 7: Gemini Multimodal Vision Analysis Function")
    dummy_img_bytes = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    vision_out = trust_engine.analyze_image_with_vision(dummy_img_bytes, "image/gif", "Fire", "Smoke and sparks from transformer")
    assert "authentic" in vision_out
    assert "risk" in vision_out
    assert "score_delta" in vision_out
    print(f" -> PASSED: Multimodal Vision responded with schema: risk={vision_out['risk']}, delta={vision_out['score_delta']}.")
    passed += 1

    # 8. Test Category-Isolated Spatial Clustering
    print("\nTest 8: Category-Isolated Spatial Clustering")
    # Same coordinate (KIIT Square 20.3533, 85.8189) but DIFFERENT category ("Assault" vs "Fire")
    separate_res = trust_engine.process_new_report(
        user_id="usr_peter",
        category="Assault",
        description="Physical altercation near the juice stall opposite the substation.",
        lat=20.3533,
        lng=85.8189,
        is_spatial=1,
        image_url=""
    )
    assert separate_res["status"] == "success"
    assert separate_res["incident_id"] != 1, f"Category isolation failed! Assault merged into Fire #1! Got {separate_res['incident_id']}"
    print(f" -> PASSED: Category isolation verified! Different category at same coordinates created new incident #{separate_res['incident_id']} (did NOT corrupt Fire #1).")
    passed += 1

    # 9. Test Negative Corroboration (On-Scene Dispute Engine)
    print("\nTest 9: Negative Corroboration On-Scene Dispute Engine")
    pre_dispute_inc = client.get("/api/incidents/1").json()
    pre_score = pre_dispute_inc["confidence_score"]

    disp_res = client.post(
        "/api/incidents/1/dispute",
        data={"note": "I am standing at KIIT Square right now; there is zero fire or smoke, false claim."},
        cookies=peter_cookies
    )
    assert disp_res.status_code == 200
    disp_json = disp_res.json()
    assert disp_json["status"] == "success"
    assert disp_json["score"] < pre_score, f"Expected score deduction, pre: {pre_score}, post: {disp_json['score']}"
    assert disp_json["dispute_count"] >= 1
    print(f" -> PASSED: On-scene dispute successfully penalized trust score ({pre_score} -> {disp_json['score']}) and logged refutation.")
    passed += 1

    # 10. Test Time-Based Freshness Score Decay
    print("\nTest 10: Time-Based Freshness Score Decay")
    stale_incident = {
        "id": 99,
        "title": "Stale Transformer Leak",
        "confidence_score": 80,
        "status": "CORROBORATED",
        "updated_at": (datetime.now() - timedelta(hours=5)).isoformat(),
        "explainability_json": "[]"
    }
    decayed = trust_engine.apply_time_decay(stale_incident)
    assert decayed["confidence_score"] < 80, f"Expected decayed score < 80, got {decayed['confidence_score']}"
    assert "Signal freshness decay" in decayed["explainability_json"]
    print(f" -> PASSED: Incident older than 4 hours received freshness decay penalty (80 -> {decayed['confidence_score']}).")
    passed += 1

    # 11. Test Rate Limiting Throttling (429 Enforcement)
    print("\nTest 11: In-Memory Sliding-Window Rate Limiting")
    # Pete Parker already submitted reports; let's test submitting rapid reports until 429
    got_429 = False
    for i in range(5):
        spam_res = client.post(
            "/api/reports",
            data={
                "category": "Obstruction",
                "description": f"Rapid spam test submission #{i}",
                "latitude": 20.3000,
                "longitude": 85.8000,
                "is_spatial": 1
            },
            cookies=peter_cookies
        )
        if spam_res.status_code == 429:
            got_429 = True
            break

    assert got_429, "Rate limiter did not trigger HTTP 429 after rapid report filings!"
    print(" -> PASSED: Rate limiter successfully blocked rapid submissions with HTTP 429 Too Many Requests.")
    passed += 1

    # 12. Test 5-Tier Status Progression (No Auto-Verify Without Authority)
    print("\nTest 12: 5-Tier Verification Lifecycle (No Auto-Verify Without Authority)")
    main.REPORT_RATE_LIMIT.clear()
    main.SUBNET_RATE_LIMIT.clear()

    editor_login = client.post("/api/auth/login", data={"username": "editor", "password": "admin123"})
    editor_cookies = editor_login.cookies

    fresh_report = client.post(
        "/api/reports",
        data={
            "category": "Civic",
            "description": "Minor water leak near Patia chowk.",
            "latitude": 20.3600,
            "longitude": 85.8200,
            "is_spatial": 1,
            "injuries": "NONE",
            "threat_state": "ACTIVE"
        },
        cookies=editor_cookies
    )
    assert fresh_report.status_code == 200
    fresh_inc_id = fresh_report.json()["incident_id"]
    fresh_inc = client.get(f"/api/incidents/{fresh_inc_id}").json()
    assert fresh_inc["status"] in ["UNVERIFIED", "COMMUNITY", "CORROBORATED"], f"Report should not be auto-verified! Got: {fresh_inc['status']}"
    assert fresh_inc["status"] != "VERIFIED", "CRITICAL FLAW: Report was auto-promoted to VERIFIED without authority dispatch!"
    print(f" -> PASSED: New report initialized with status '{fresh_inc['status']}' without unauthorized auto-verification.")
    passed += 1

    # 13. Test Semantic Stance & Contradiction Detection (Natural Language Inference)
    print("\nTest 13: Semantic Stance & Eyewitness Contradiction Detection")
    main.REPORT_RATE_LIMIT.clear()
    main.SUBNET_RATE_LIMIT.clear()

    # Step A: Citizen reports a fire
    inc_claim = trust_engine.process_new_report(
        user_id="usr_peter",
        category="Fire",
        description="Massive blaze erupting at City Center food court!",
        lat=20.2950,
        lng=85.8250,
        is_spatial=1,
        image_url="",
        client_ip="10.0.0.1"
    )
    fire_inc_id = inc_claim["incident_id"]
    score_before_contradiction = inc_claim["score"]

    # Step B: Second citizen files refutation at same coordinates
    contra_claim = trust_engine.process_new_report(
        user_id="usr_dispatcher",
        category="Fire",
        description="I am standing right at City Center food court, there is no fire at all, false alarm and normal business.",
        lat=20.2950,
        lng=85.8250,
        is_spatial=1,
        image_url="",
        client_ip="10.0.0.2"
    )
    assert contra_claim["status"] == "disputed"
    assert contra_claim["stance"] == "CONTRADICTING"
    assert contra_claim["score"] < score_before_contradiction, f"Contradiction should reduce score! Pre: {score_before_contradiction}, Post: {contra_claim['score']}"

    # Verify disputes table has this refutation
    disputes = database.get_incident_disputes(fire_inc_id)
    assert len(disputes) >= 1
    assert "there is no fire at all" in disputes[0]["note"]
    print(f" -> PASSED: Refutation correctly classified as CONTRADICTING, routed to disputes ledger, docked score ({score_before_contradiction} -> {contra_claim['score']}).")
    passed += 1

    # 14. Test Anti-Sybil Subnet Clustering & Device Fingerprinting
    print("\nTest 14: Anti-Sybil Subnet Clustering (Same /24 Subnet Collapsing)")
    main.REPORT_RATE_LIMIT.clear()
    main.SUBNET_RATE_LIMIT.clear()

    # Submitting 3 reports from distinct users but all within the same /24 subnet (192.168.1.*)
    sybil_1 = trust_engine.process_new_report(
        user_id="usr_sybil_1",
        category="Obstruction",
        description="Downed electrical pole blocking lane 1.",
        lat=20.3100,
        lng=85.8300,
        is_spatial=1,
        image_url="",
        client_ip="192.168.1.10",
        device_hash="bot_device_1"
    )
    sybil_inc_id = sybil_1["incident_id"]

    sybil_2 = trust_engine.process_new_report(
        user_id="usr_sybil_2",
        category="Obstruction",
        description="Downed electrical pole blocking lane 1 confirmed.",
        lat=20.3100,
        lng=85.8300,
        is_spatial=1,
        image_url="",
        client_ip="192.168.1.11",
        device_hash="bot_device_1"
    )

    sybil_3 = trust_engine.process_new_report(
        user_id="usr_sybil_3",
        category="Obstruction",
        description="Downed electrical pole still blocking lane 1.",
        lat=20.3100,
        lng=85.8300,
        is_spatial=1,
        image_url="",
        client_ip="192.168.1.12",
        device_hash="bot_device_1"
    )

    conn = database.get_connection()
    sybil_inc = conn.execute("SELECT * FROM incidents WHERE id = ?", (sybil_inc_id,)).fetchone()
    conn.close()

    # Even though 3 distinct accounts submitted, they all belong to 192.168.1.0/24 and bot_device_1
    assert sybil_inc["source_diversity"] == 1, f"Expected 1 source diversity for same subnet/device, got {sybil_inc['source_diversity']}"
    print(f" -> PASSED: Anti-Sybil engine successfully collapsed 3 bot accounts from 192.168.1.* into a single source diversity credit.")
    passed += 1

    # 15. Test Automated PII & Defamation Redaction Guardrail
    print("\nTest 15: Automated PII & Defamation Redaction Guardrail")
    raw_defamatory = "Illegal narcotics ring run by Mr. Rajesh Verma at Flat 402, Lotus Heights. Call 9876543210 for information."
    sanitized_text, was_redacted = trust_engine.sanitize_pii_and_defamation(raw_defamatory)

    assert was_redacted is True
    assert "Rajesh Verma" not in sanitized_text
    assert "Flat 402" not in sanitized_text
    assert "9876543210" not in sanitized_text
    assert "[REDACTED INDIVIDUAL]" in sanitized_text
    assert "[REDACTED RESIDENCE]" in sanitized_text
    assert "[REDACTED CONTACT]" in sanitized_text
    print(f" -> PASSED: PII/Defamation guardrail successfully sanitized personal name, flat number, and contact info.")
    passed += 1

    # 16. Test Cryptographic Image Provenance & EXIF Temporal Audit
    print("\nTest 16: Cryptographic Image Provenance (dHash) & EXIF Temporal Audit")
    import io
    from PIL import Image

    # 16a. Test Old EXIF Image
    img_old = Image.new("RGB", (120, 120), color="orange")
    exif_old = img_old.getexif()
    old_date = (datetime.now() - timedelta(days=2)).strftime("%Y:%m:%d %H:%M:%S")
    exif_old[306] = old_date
    buf_old = io.BytesIO()
    img_old.save(buf_old, format="JPEG", exif=exif_old)
    old_bytes = buf_old.getvalue()

    forensics_old = trust_engine.compute_image_dhash_and_exif(old_bytes)
    assert forensics_old["valid"] is False
    assert forensics_old["risk"] == "TEMPORAL_MISMATCH"
    assert forensics_old["score_delta"] == -25
    print(f" -> PASSED (Part A): 2-day-old photo detected via EXIF metadata: {forensics_old['explanation']}.")

    # 16b. Test Recycled Media Detection via dHash
    img_clean = Image.new("RGB", (120, 120), color="green")
    buf_clean = io.BytesIO()
    img_clean.save(buf_clean, format="JPEG")
    clean_bytes = buf_clean.getvalue()

    # First upload: should pass and register hash
    forensics_clean = trust_engine.compute_image_dhash_and_exif(clean_bytes)
    assert forensics_clean["valid"] is True
    database.record_image_hash(forensics_clean["image_hash"], 1)

    # Second upload of exact same media: should trigger RECYCLED
    forensics_recycled = trust_engine.compute_image_dhash_and_exif(clean_bytes)
    assert forensics_recycled["valid"] is False
    assert forensics_recycled["risk"] == "RECYCLED"
    assert forensics_recycled["score_delta"] == -35
    print(f" -> PASSED (Part B): Recycled image detected and penalized -35 points via perceptual dHash.")
    passed += 1

    # 17. Test Lethality Priority Matrix & Decay Exemption
    print("\nTest 17: Lethality Priority Matrix & Freshness Decay Exemption")
    main.REPORT_RATE_LIMIT.clear()
    main.SUBNET_RATE_LIMIT.clear()

    hazmat_res = trust_engine.process_new_report(
        user_id="usr_peter",
        category="Disaster",
        description="Catastrophic toxic chlorine chemical leak with multiple confirmed casualties.",
        lat=20.2800,
        lng=85.8100,
        is_spatial=1,
        image_url="",
        injuries="CONFIRMED",
        threat_state="ACTIVE",
        client_ip="10.50.0.1"
    )
    hazmat_id = hazmat_res["incident_id"]

    conn = database.get_connection()
    hazmat_inc = conn.execute("SELECT * FROM incidents WHERE id = ?", (hazmat_id,)).fetchone()
    conn.close()

    assert hazmat_inc["is_lethal_priority"] == 1, "Incident with confirmed casualties should have is_lethal_priority=1!"

    # Simulate 4.5 hours elapsed: normal incident decays, but lethal hazard is exempt!
    stale_hazmat = dict(hazmat_inc)
    stale_hazmat["updated_at"] = (datetime.now() - timedelta(hours=4.5)).isoformat()
    non_decayed = trust_engine.apply_time_decay(stale_hazmat)
    assert non_decayed["confidence_score"] == hazmat_inc["confidence_score"], "Lethal hazard should be exempt from premature time decay!"
    print(f" -> PASSED: HAZMAT emergency granted lethal priority and protected from decay suppression for 6 hours.")
    passed += 1

    print(f"\n=======================================================")
    print(f" [ALL {passed}/{total} TESTS PASSED SUCCESSFULLY!]")
    print("=======================================================\n")

if __name__ == "__main__":
    test_suite()

