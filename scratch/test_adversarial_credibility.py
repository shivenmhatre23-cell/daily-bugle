import sys
import os
import json
import sqlite3
import io
from datetime import datetime, timedelta
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database
import trust_engine

TEST_DB = "scratch/test_adversarial.db"

def setup_test_db():
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except Exception:
            pass
    database.DB_PATH = TEST_DB
    database.init_db()

    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    users = [
        ("usr_ed", "editor_test", "Editor Jane", "ed@test.com", "+919000000001", "hash", "EDITOR", 1, 1.0, 0, 0, now),
        ("usr_cit1", "cit_1", "Citizen One", "cit1@test.com", "+919000000002", "hash", "CITIZEN", 1, 0.9, 0, 0, now),
        ("usr_cit2", "cit_2", "Citizen Two", "cit2@test.com", "+919000000003", "hash", "CITIZEN", 1, 0.85, 0, 0, now),
        ("usr_cit3", "cit_3", "Citizen Three", "cit3@test.com", "+919000000004", "hash", "CITIZEN", 1, 0.8, 0, 0, now),
        ("usr_troll1", "troll_1", "Troll One", "troll1@test.com", "+919000000005", "hash", "CITIZEN", 0, 0.1, 0, 0, now),
        ("usr_troll2", "troll_2", "Troll Two", "troll2@test.com", "+919000000006", "hash", "CITIZEN", 0, 0.1, 0, 0, now),
    ]
    cursor.executemany("""
        INSERT INTO users (id, username, name, email, phone, password_hash, role, is_verified, trust_score, strike_count, is_quarantined, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, users)
    conn.commit()
    conn.close()

def create_synthetic_image(with_fresh_exif: bool = False) -> bytes:
    img = Image.new("RGB", (200, 200), color=(255, 75, 40))
    buf = io.BytesIO()
    if with_fresh_exif:
        exif = img.getexif()
        exif[271] = "BugleForensicsCam"
        exif[272] = "Model-X"
        exif[306] = datetime.now().strftime("%Y:%m:%d %H:%M:%S")
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()

def run_tests():
    print("=" * 70)
    print("RUNNING ADVERSARIAL CREDIBILITY SUITE")
    print("=" * 70)
    setup_test_db()

    # TEST 1: Missing EXIF Neutralization
    print("\n[TEST 1] Missing-EXIF Vulnerability Neutralization...")
    img_no_exif = create_synthetic_image(with_fresh_exif=False)
    audit_no_exif = trust_engine.compute_image_dhash_and_exif(img_no_exif)
    assert audit_no_exif["risk"] == "UNATTESTED_METADATA", f"Expected UNATTESTED_METADATA, got {audit_no_exif['risk']}"
    assert audit_no_exif["score_delta"] == 0, f"Expected score_delta 0, got {audit_no_exif['score_delta']}"
    assert "EXIF temporal metadata absent" in audit_no_exif["explanation"]
    print("  -> PASSED: Image without EXIF headers received 0 bonus points (UNATTESTED_METADATA).")

    # TEST 2: Genuine Fresh EXIF Verification
    print("\n[TEST 2] Fresh EXIF Camera Telemetry Verification...")
    img_with_exif = create_synthetic_image(with_fresh_exif=True)
    audit_exif = trust_engine.compute_image_dhash_and_exif(img_with_exif)
    assert audit_exif["risk"] == "EXIF_FRESH", f"Expected EXIF_FRESH, got {audit_exif['risk']}"
    assert audit_exif["score_delta"] == 10, f"Expected score_delta 10, got {audit_exif['score_delta']}"
    assert "EXIF Temporal freshness verified" in audit_exif["explanation"]
    print("  -> PASSED: Genuine fresh camera EXIF received earned +10 bonus points (EXIF_FRESH).")

    # TEST 3: Anti-Brigading Dispute Quorum
    print("\n[TEST 3] Anti-Brigading Quorum Defense against Troll Attacks...")
    res1 = trust_engine.process_new_report(
        user_id="usr_cit1",
        category="Fire",
        description="Massive structural blaze at commercial warehouse on Cuttack Road.",
        lat=20.2850,
        lng=85.8450,
        is_spatial=1,
        image_url="",
        client_ip="103.21.244.11",
        device_hash="dev_cit1"
    )
    inc_id = res1["incident_id"]

    trust_engine.corroborate_existing_incident(
        incident_id=inc_id,
        user_id="usr_cit2",
        note="Warehouse roof actively collapsing, heavy smoke blowing west.",
        client_ip="103.21.244.12",
        device_hash="dev_cit2"
    )
    trust_engine.corroborate_existing_incident(
        incident_id=inc_id,
        user_id="usr_cit3",
        note="Fire engine 101 attempting access from north alley.",
        client_ip="103.21.244.13",
        device_hash="dev_cit3"
    )

    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT status, confidence_score, report_count FROM incidents WHERE id = ?", (inc_id,))
    row = dict(c.fetchone())
    conn.close()

    assert row["report_count"] == 3
    assert row["status"] in ["CORROBORATED", "COMMUNITY"], f"Expected cluster status, got {row['status']}"
    initial_score = row["confidence_score"]
    print(f"  -> Initial verified cluster established: status={row['status']}, score={initial_score}")

    # 2 unverified guest trolls attempt to suppress the alert
    disp1 = trust_engine.submit_scene_dispute(inc_id, "usr_troll1", "Fake news! There is no fire here, clear roads.")
    assert disp1["quorum_met"] is False, "Troll 1 should NOT have triggered quorum"

    disp2 = trust_engine.submit_scene_dispute(inc_id, "usr_troll2", "Nothing happening at this location. Delete this post.")
    assert disp2["quorum_met"] is False, "2 Trolls should NOT have triggered quorum against 3 verified citizens"

    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT status, confidence_score, dispute_count FROM incidents WHERE id = ?", (inc_id,))
    row_disputed = dict(c.fetchone())
    conn.close()

    assert row_disputed["dispute_count"] == 2
    assert row_disputed["status"] == row["status"], f"Status was suppressed to {row_disputed['status']}! Anti-brigading failed!"
    print(f"  -> Anti-brigading protected cluster: Status preserved as '{row_disputed['status']}' despite 2 troll disputes!")

    # A verified citizen refutes on-scene (W_disp >= 0.35 * W_corr)
    disp3 = trust_engine.submit_scene_dispute(inc_id, "usr_cit1", "Update from location: fire was contained 10 mins ago, no current active flames.")
    assert disp3["quorum_met"] is True, "Verified citizen dispute should meet quorum"
    assert disp3["incident"]["status"] == "SUSPICIOUS", f"Expected SUSPICIOUS on quorum, got {disp3['incident']['status']}"
    print("  -> Legit verified on-scene refutation satisfied quorum -> flipped to SUSPICIOUS.")

    # TEST 4: Synthetic Micro-Cluster Detection
    print("\n[TEST 4] Synthetic Micro-Cluster (Cloned Bot Submissions) Detection...")
    res_bot1 = trust_engine.process_new_report(
        user_id="usr_troll1",
        category="Civic",
        description="Fallen power pole sparking near square.",
        lat=20.350000,
        lng=85.820000,
        is_spatial=1,
        image_url="",
        client_ip="185.220.101.5",
        device_hash="bot_hardware_1"
    )
    bot_inc_id = res_bot1["incident_id"]

    trust_engine.corroborate_existing_incident(
        incident_id=bot_inc_id,
        user_id="usr_troll2",
        note="Fallen pole sparking near square.",
        client_ip="185.220.101.6",
        device_hash="bot_hardware_2"
    )

    conn = database.get_connection()
    c = conn.cursor()
    c.execute("UPDATE reports SET latitude = 20.350001, longitude = 85.820001 WHERE incident_id = ? AND user_id = 'usr_troll2'", (bot_inc_id,))
    conn.commit()
    conn.close()

    bot_matrix = trust_engine.compute_credibility_matrix(bot_inc_id)
    geo_vector = bot_matrix["vectors"]["geospatial_grounding"]
    assert geo_vector["risk"] == "SYNTHETIC_MICRO_CLUSTER", f"Expected SYNTHETIC_MICRO_CLUSTER, got {geo_vector['risk']}"
    assert geo_vector["score"] == 0.25, f"Expected 0.25 score, got {geo_vector['score']}"
    assert geo_vector["grade"] == "COMPROMISED"
    print("  -> PASSED: Identical coordinates (<5m spread) flagged as SYNTHETIC_MICRO_CLUSTER (score=0.25, COMPROMISED).")

    # TEST 5: Sybil Subnet Collusion Detection
    print("\n[TEST 5] Sybil Collusion Detection (Identical Device/IP)...")
    res_sybil = trust_engine.process_new_report(
        user_id="usr_troll1",
        category="Assault",
        description="Fight broke out near bus stand.",
        lat=20.3100,
        lng=85.8200,
        is_spatial=1,
        image_url="",
        client_ip="192.168.1.100",
        device_hash="sybil_dev_clone"
    )
    sybil_inc_id = res_sybil["incident_id"]

    trust_engine.corroborate_existing_incident(
        incident_id=sybil_inc_id,
        user_id="usr_troll2",
        note="Fight near bus stand.",
        client_ip="192.168.1.100",
        device_hash="sybil_dev_clone"
    )

    sybil_matrix = trust_engine.compute_credibility_matrix(sybil_inc_id)
    source_vector = sybil_matrix["vectors"]["source_independence"]
    assert source_vector["risk"] == "SYBIL_COLLUSION_SUSPECTED", f"Expected SYBIL_COLLUSION_SUSPECTED, got {source_vector['risk']}"
    assert source_vector["score"] == 0.20, f"Expected 0.20 score, got {source_vector['score']}"
    assert source_vector["grade"] == "COMPROMISED"
    print("  -> PASSED: Cloned IP/Device reports flagged as SYBIL_COLLUSION_SUSPECTED (score=0.20, COMPROMISED).")

    # TEST 6: Invariant: Decoupled Confidence vs Ground Truth Certainty
    print("\n[TEST 6] Ground Truth Invariant: Confidence Score != Truth Certainty...")
    matrix_check = trust_engine.compute_credibility_matrix(inc_id)
    gt = matrix_check["ground_truth"]
    assert "High algorithmic confidence indicates reporting density" in gt["epistemic_warning"]
    print("  -> PASSED: Ground Truth Attestation cleanly separates confidence from physical reality.")
    print(f"     Attestation: {gt['reality_badge']}")

    print("\n" + "=" * 70)
    print("ALL ADVERSARIAL CREDIBILITY TESTS PASSED SUCCESSFULLY! (6/6)")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
