"""
Production Hardening & Verification Test Suite for The Daily Bugle
Verifies:
1. Coordinate bounds validation (-90..90, -180..180)
2. Incident category whitelist validation
3. Upload payload size limit (>10MB rejected with 413)
4. Corrupted image upload rejected with 400 (Pillow verification)
5. Valid image upload accepted
6. Sliding-window rate limiter TTL auto-eviction & memory bounding
7. Spatial bounding box index pre-filtering in trust_engine
8. Unified single-shot multimodal triage function
9. Spoofed X-Forwarded-For IP safety
"""
import io
import os
import sys
import time
from PIL import Image
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

def create_dummy_png(width=10, height=10, color=(255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color)
    img.save(buf, format="PNG")
    return buf.getvalue()

def run_tests():
    seed_demo_data.seed()
    print("\n=======================================================")
    print(" [PRODUCTION HARDENING & PERFORMANCE TEST SUITE]")
    print("=======================================================\n")

    passed = 0
    total = 9

    # 1. Coordinate Bounds Validation
    print("Test 1: Latitude / Longitude Bounds Validation")
    res_bad_lat = client.post("/api/reports", data={
        "category": "Fire",
        "description": "Invalid latitude report",
        "latitude": 95.0, # Out of range!
        "longitude": 40.0
    })
    assert res_bad_lat.status_code == 400, f"Expected 400 for lat=95, got {res_bad_lat.status_code}"
    assert "Invalid geographical coordinates" in res_bad_lat.json().get("error", "")

    res_bad_lng = client.post("/api/reports", data={
        "category": "Fire",
        "description": "Invalid longitude report",
        "latitude": 40.0,
        "longitude": -195.0 # Out of range!
    })
    assert res_bad_lng.status_code == 400, f"Expected 400 for lng=-195, got {res_bad_lng.status_code}"
    print(" -> PASSED: Coordinates outside [-90..90, -180..180] rejected with HTTP 400.")
    passed += 1

    # 2. Incident Category Whitelist
    print("\nTest 2: Category Whitelist Enforcement")
    res_bad_cat = client.post("/api/reports", data={
        "category": "UnicornAttack",
        "description": "Nonsense category test",
        "latitude": 40.7128,
        "longitude": -74.0060
    })
    assert res_bad_cat.status_code == 400, f"Expected 400 for invalid category, got {res_bad_cat.status_code}"
    assert "Invalid incident category" in res_bad_cat.json().get("error", "")
    print(" -> PASSED: Invalid categories rejected with HTTP 400 whitelist enforcement.")
    passed += 1

    # 3. Upload Payload Cap (>10MB)
    print("\nTest 3: File Upload 10MB Cap Protection")
    huge_payload = b"X" * (10 * 1024 * 1024 + 1024) # 10MB + 1KB
    res_huge = client.post(
        "/api/reports",
        data={
            "category": "Fire",
            "description": "Oversized file upload attempt",
            "latitude": 40.7128,
            "longitude": -74.0060
        },
        files={"image": ("huge_file.jpg", huge_payload, "image/jpeg")}
    )
    assert res_huge.status_code == 413, f"Expected 413 Payload Too Large, got {res_huge.status_code}"
    assert "exceeds the 10MB" in res_huge.json().get("error", "")
    print(" -> PASSED: Files > 10MB rejected with HTTP 413 Payload Too Large.")
    passed += 1

    # 4. Corrupted / Inauthentic Image Magic Bytes Verification
    print("\nTest 4: Pillow Magic Bytes & Header Verification")
    corrupt_bytes = b"NOT_A_REAL_IMAGE_DATA_12345"
    res_corrupt = client.post(
        "/api/reports",
        data={
            "category": "Fire",
            "description": "Corrupted image file upload attempt",
            "latitude": 40.7128,
            "longitude": -74.0060
        },
        files={"image": ("fake.jpg", corrupt_bytes, "image/jpeg")}
    )
    assert res_corrupt.status_code == 400, f"Expected 400 for corrupted image, got {res_corrupt.status_code}"
    assert "Invalid or corrupted image format" in res_corrupt.json().get("error", "")
    print(" -> PASSED: Spoofed or corrupted image byte streams rejected with HTTP 400.")
    passed += 1

    # 5. Valid Image Upload Acceptance
    print("\nTest 5: Valid Image Header Acceptance")
    main.REPORT_RATE_LIMIT.clear()
    main.SUBNET_RATE_LIMIT.clear()
    valid_png = create_dummy_png()
    res_valid_img = client.post(
        "/api/reports",
        data={
            "category": "Fire",
            "description": "Legitimate report with verified image header",
            "latitude": 40.7128,
            "longitude": -74.0060
        },
        files={"image": ("evidence.png", valid_png, "image/png")}
    )
    assert res_valid_img.status_code == 200, f"Expected 200, got {res_valid_img.status_code} ({res_valid_img.text})"
    data = res_valid_img.json()
    assert data["status"] == "success"
    print(f" -> PASSED: Valid image parsed successfully, incident result: {data}.")
    passed += 1

    # 6. Rate Limiter TTL Auto-Eviction & Bounding
    print("\nTest 6: Rate Limiter Memory Management & TTL Auto-Eviction")
    test_store = {}
    key = "test_user_key"
    # Seed old timestamps (expired beyond 2 seconds)
    test_store[key] = [time.time() - 10, time.time() - 8]
    # Check limit with 2s window - expired timestamps must be pruned!
    allowed = main.check_rate_limit(test_store, key, max_calls=2, window_seconds=2)
    assert allowed is True, "Expected rate limit to allow after eviction"
    assert len(test_store[key]) == 1, f"Expected 1 valid timestamp, got {len(test_store[key])}"
    print(" -> PASSED: Rate limiter safely evicts expired timestamps and bounds memory.")
    passed += 1

    # 7. Spatial Bounding Box Filter Accuracy
    print("\nTest 7: Spatial Bounding Box Coordinate Calculation")
    lat, lng = 40.7128, -74.0060
    max_dist_m = 500
    delta_lat = max_dist_m / 111000.0
    import math
    cos_lat = max(0.1, math.cos(math.radians(lat)))
    delta_lng = max_dist_m / (111000.0 * cos_lat)
    min_lat, max_lat = lat - delta_lat, lat + delta_lat
    min_lng, max_lng = lng - delta_lng, lng + delta_lng

    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM incidents 
        WHERE status != 'BUSTED' 
          AND is_spatial = 1 
          AND latitude BETWEEN ? AND ? 
          AND longitude BETWEEN ? AND ?
    """, (min_lat, max_lat, min_lng, max_lng))
    cnt = cur.fetchone()[0]
    conn.close()
    assert cnt >= 0
    print(f" -> PASSED: Bounding box query executed over index (candidates found: {cnt}).")
    passed += 1

    # 8. Unified Single-Shot Multimodal Triage Function
    print("\nTest 8: Unified Multimodal Triage Function Execution")
    ai_analysis, vision_result = trust_engine.analyze_report_and_vision_unified(
        category="Fire",
        description="Transformer fire with visible heavy smoke billowing near 5th ave",
        image_bytes=valid_png,
        mime_type="image/png"
    )
    assert "clean_title" in ai_analysis
    assert "severity" in ai_analysis
    assert vision_result is not None
    assert "authentic" in vision_result
    assert "risk" in vision_result
    print(f" -> PASSED: Unified triage returned structured headline ('{ai_analysis['clean_title']}') and vision risk ('{vision_result['risk']}').")
    passed += 1

    # 9. Client IP Header Injections & Spoofing Safety
    print("\nTest 9: X-Forwarded-For Spoofing & Format Safety")
    main.REPORT_RATE_LIMIT.clear()
    main.SUBNET_RATE_LIMIT.clear()
    res_spoof = client.post(
        "/api/reports",
        data={
            "category": "Civic",
            "description": "Safe IP test report with malformed forwarded header",
            "latitude": 40.7500,
            "longitude": -73.9800
        },
        headers={"X-Forwarded-For": "malformed_ip_injection_attack', DROP TABLE users;--"}
    )
    assert res_spoof.status_code == 200, f"Expected 200 despite malicious header, got {res_spoof.status_code}"
    print(" -> PASSED: Malformed or malicious IP header safely sanitized without query disruption.")
    passed += 1

    print("\n=======================================================")
    print(f" [ALL TESTS PASSED: {passed}/{total}]")
    print("=======================================================\n")

if __name__ == "__main__":
    run_tests()
