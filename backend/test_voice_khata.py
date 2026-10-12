"""
Test Suite for Voice Khata Entry, AI Transaction Parsing, Customer Resolution, and Idempotency.
"""
import subprocess
import time
import urllib.request
import urllib.error
import json
import os
import sys

def run_tests():
    print("Starting Voice Khata test suite...")
    db_path = "c:/Srikar/Khata App/backend/udhara.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        print("Removed existing test database.")

    cmd = [
        "c:/Srikar/Khata App/backend/.venv/Scripts/python.exe",
        "-m", "uvicorn", 
        "main:app", 
        "--host", "127.0.0.1", 
        "--port", "8005"
    ]
    
    server_process = subprocess.Popen(
        cmd,
        cwd="c:/Srikar/Khata App/backend"
    )
    
    time.sleep(3)
    
    if server_process.poll() is not None:
        print("Error: Server failed to start.")
        sys.exit(1)

    base_url = "http://127.0.0.1:8005"
    
    def request(path, method="GET", data=None, token=None, extra_headers=None):
        url = f"{base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if extra_headers:
            headers.update(extra_headers)
            
        req_data = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                body = res.read().decode("utf-8")
                return res.status, json.loads(body) if body else None
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            try:
                body_json = json.loads(body)
            except Exception:
                body_json = body
            return e.code, body_json

    try:
        # 1. Setup Store A and Store B
        print("1. Creating Stores for multi-tenant isolation...")
        status, store_a = request("/api/stores", "POST", {
            "store_name": "Store Alpha",
            "owner_name": "Alpha Owner",
            "pin": "1111",
            "language": "te",
            "recovery_question": "Pet?",
            "recovery_answer": "Dog"
        })
        assert status == 201
        token_a = store_a["token"]

        status, store_b = request("/api/stores", "POST", {
            "store_name": "Store Beta",
            "owner_name": "Beta Owner",
            "pin": "2222",
            "language": "en",
            "recovery_question": "Pet?",
            "recovery_answer": "Cat"
        })
        assert status == 201
        token_b = store_b["token"]

        # 2. Create Customers
        print("2. Creating customers in Store A and Store B...")
        # Store A customers
        status, c_ramesh_a = request("/api/customers", "POST", {"name": "Ramesh Kumar", "phone": "9876543210"}, token=token_a)
        assert status == 201
        status, c_suresh_a = request("/api/customers", "POST", {"name": "Suresh Rao", "phone": "9123456780"}, token=token_a)
        assert status == 201
        # Store B customer with same name "Ramesh"
        status, c_ramesh_b = request("/api/customers", "POST", {"name": "Ramesh Gupta", "phone": "9998887776"}, token=token_b)
        assert status == 201

        # 3. Test Voice Transcription endpoint with mock header
        print("3. Testing POST /api/voice/transcribe...")
        status, tr_resp = request(
            "/api/voice/transcribe",
            "POST",
            extra_headers={"X-Mock-Transcript": "Ramesh ki 2 kilo rice, 1 oil packet, 150 rupees udhar raayi"},
            token=token_a
        )
        assert status == 200
        assert tr_resp["transcript"] == "Ramesh ki 2 kilo rice, 1 oil packet, 150 rupees udhar raayi"
        assert tr_resp["provider"] == "mock"

        # 4. Test Voice Parsing with mixed phrase (Credit)
        print("4. Testing POST /api/voice/parse (Credit with items and explicit total)...")
        status, parse_resp = request(
            "/api/voice/parse",
            "POST",
            {"transcript": "Ramesh ki 2 kilo rice, 1 oil packet, 150 rupees udhar raayi"},
            token=token_a
        )
        assert status == 200
        draft = parse_resp["draft"]
        assert draft["customer_name_spoken"] == "Ramesh"
        assert draft["transaction_type"] == "credit"
        assert draft["amount_rupees"] == 150.0
        assert draft["amount_paise"] == 15000
        assert len(draft["items"]) >= 1
        assert "Rice" in draft["note"] or "rice" in draft["note"]
        assert draft["clarification_required"] is False
        
        # Check Customer Matching within Store A
        match = parse_resp["customer_match"]
        assert match["matched_customer"] is not None
        assert match["matched_customer"]["id"] == c_ramesh_a["id"]
        assert match["matched_customer"]["name"] == "Ramesh Kumar"
        assert match["clarification_required"] is False

        # 5. Verify Store Isolation in Customer Matching
        print("5. Testing tenant isolation in customer matching...")
        # Store B parsing "Suresh" (which only exists in Store A)
        status, parse_b = request(
            "/api/voice/parse",
            "POST",
            {"transcript": "Suresh ki 200 rupees udhar"},
            token=token_b
        )
        assert status == 200
        # Should NOT match Suresh from Store A!
        assert parse_b["customer_match"]["matched_customer"] is None
        assert parse_b["customer_match"]["clarification_required"] is True

        # 6. Test Voice Parsing (Payment)
        print("6. Testing POST /api/voice/parse (Payment)...")
        status, parse_pay = request(
            "/api/voice/parse",
            "POST",
            {"transcript": "Ramesh 200 rupees pay chesadu"},
            token=token_a
        )
        assert status == 200
        assert parse_pay["draft"]["transaction_type"] == "payment"
        assert parse_pay["draft"]["amount_rupees"] == 200.0
        assert parse_pay["draft"]["amount_paise"] == 20000

        # 7. Test Missing Fields Handling
        print("7. Testing missing amount and missing transaction type...")
        # Missing amount
        status, parse_no_amt = request(
            "/api/voice/parse",
            "POST",
            {"transcript": "Ramesh ki udhar raayi"},
            token=token_a
        )
        assert status == 200
        assert "amount" in parse_no_amt["draft"]["missing_fields"]
        assert parse_no_amt["draft"]["clarification_required"] is True

        # Missing transaction type
        status, parse_no_type = request(
            "/api/voice/parse",
            "POST",
            {"transcript": "Ramesh 500"},
            token=token_a
        )
        assert status == 200
        assert "transaction_type" in parse_no_type["draft"]["missing_fields"]
        assert parse_no_type["draft"]["clarification_required"] is True

        # 8. Test Ambiguous Customers Matching
        print("8. Testing ambiguous customers matching...")
        # Create second Ramesh in Store A
        status, c_ramesh_2 = request("/api/customers", "POST", {"name": "Ramesh Yadav", "phone": "9444332211"}, token=token_a)
        assert status == 201
        
        status, parse_ambig = request(
            "/api/voice/parse",
            "POST",
            {"transcript": "Ramesh 100 udhar"},
            token=token_a
        )
        assert status == 200
        # Since both "Ramesh Kumar" and "Ramesh Yadav" exist, clarification must be required
        assert parse_ambig["customer_match"]["matched_customer"] is None
        assert parse_ambig["customer_match"]["clarification_required"] is True
        assert len(parse_ambig["customer_match"]["candidates"]) >= 2

        # 9. Test Idempotent Transaction Confirmation & Balance Calculation
        print("9. Testing Idempotent Transaction Creation & Authoritative Balance...")
        idempotency_key = "test_key_voice_12345"
        payload = {
            "customer_id": c_ramesh_a["id"],
            "type": "credit",
            "amount": 15000,
            "note": "Rice (2 kg), Oil (1 pkt)",
            "idempotency_key": idempotency_key
        }
        status, tx_res1 = request("/api/transactions", "POST", payload, token=token_a)
        assert status == 201
        assert tx_res1["amount"] == 15000
        assert tx_res1["current_balance"] == 15000  # 150.00 rupees in paise
        assert tx_res1["idempotent_replay"] is False
        created_tx_id = tx_res1["id"]

        # Re-send exact same request with same idempotency key
        print("10. Testing Idempotent Replay...")
        status, tx_res2 = request("/api/transactions", "POST", payload, token=token_a)
        assert status == 201 or status == 200
        assert tx_res2["id"] == created_tx_id
        assert tx_res2["idempotent_replay"] is True
        assert tx_res2["current_balance"] == 15000

        # Verify only ONE transaction exists in DB
        status, cust_history = request(f"/api/transactions/{c_ramesh_a['id']}", "GET", token=token_a)
        assert status == 200
        assert cust_history["total_transactions"] == 1

        # Re-send with same idempotency key but DIFFERENT payload (Conflict)
        print("11. Testing Idempotency Conflict Detection (409 Conflict)...")
        bad_payload = {
            "customer_id": c_ramesh_a["id"],
            "type": "credit",
            "amount": 99900,  # Different amount!
            "idempotency_key": idempotency_key
        }
        status, conflict_res = request("/api/transactions", "POST", bad_payload, token=token_a)
        assert status == 409
        assert "Idempotency key reused" in conflict_res["detail"]

        print("\n=== ALL VOICE KHATA & IDEMPOTENCY TESTS PASSED 100%! ===")

    finally:
        server_process.terminate()
        server_process.wait()

if __name__ == "__main__":
    run_tests()
