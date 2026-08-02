import subprocess
import time
import urllib.request
import urllib.error
import json
import os
import sys

def run_tests():
    print("Starting FastAPI Multi-Store test server...")
    db_path = "c:/Srikar/Khata App/backend/udhara.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        print("Removed existing test database.")

    cmd = [
        "c:/Srikar/Khata App/backend/.venv/Scripts/python.exe",
        "-m", "uvicorn", 
        "main:app", 
        "--host", "127.0.0.1", 
        "--port", "8000"
    ]
    
    server_process = subprocess.Popen(
        cmd,
        cwd="c:/Srikar/Khata App/backend"
    )
    
    print("Waiting for server to start...")
    time.sleep(3)
    
    if server_process.poll() is not None:
        print("Error: Server failed to start.")
        sys.exit(1)

    print("Server started successfully.")
    
    base_url = "http://127.0.0.1:8000"
    
    # Helper request function
    def request(path, method="GET", data=None, token=None):
        url = f"{base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
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
        except Exception as e:
            print(f"Connection error to {path}: {e}")
            raise e

    try:
        # 1. Sign up Store A
        print("1. Creating Store A and Owner A...")
        status, res_a = request("/api/stores", method="POST", data={
            "store_name": "Store A",
            "owner_name": "Owner A",
            "pin": "1111",
            "recovery_question": "What is my favorite color?",
            "recovery_answer": "blue",
            "language": "en"
        })
        assert status == 201, f"Expected 201, got {status}"
        token_a = res_a["token"]
        store_a_id = res_a["store_id"]
        owner_a_id = res_a["user_id"]
        print("-> Store A created successfully.")

        # 2. Sign up Store B
        print("2. Creating Store B and Owner B...")
        status, res_b = request("/api/stores", method="POST", data={
            "store_name": "Store B",
            "owner_name": "Owner B",
            "pin": "2222",
            "recovery_question": "What is my pet's name?",
            "recovery_answer": "doggy",
            "language": "te"
        })
        assert status == 201, f"Expected 201, got {status}"
        token_b = res_b["token"]
        store_b_id = res_b["store_id"]
        owner_b_id = res_b["user_id"]
        print("-> Store B created successfully.")

        # 3. Create Customers in each store
        print("3. Creating customers...")
        status, cust_a = request("/api/customers", method="POST", data={"name": "Customer A", "phone": "9999999999"}, token=token_a)
        assert status == 201, f"Expected 201, got {status}"
        
        status, cust_b = request("/api/customers", method="POST", data={"name": "Customer B", "phone": "8888888888"}, token=token_b)
        assert status == 201, f"Expected 201, got {status}"
        print("-> Customers created.")

        # 4. Strict Isolation Check (Owner A tries to access Owner B's customer)
        print("4. Testing data isolation boundaries...")
        # GET customer B from A's token
        status, err = request(f"/api/customers/{cust_b['id']}", token=token_a)
        assert status == 404, f"Expected 404 for accessing cross-store customer, got {status}"
        print("-> Blocked GET cross-store customer.")

        # UPDATE customer B from A's token
        status, err = request(f"/api/customers/{cust_b['id']}", method="PUT", data={"name": "Hacked name"}, token=token_a)
        assert status == 404, f"Expected 404 for updating cross-store customer, got {status}"
        print("-> Blocked PUT cross-store customer.")

        # CREATE transaction for customer B from A's token
        status, err = request("/api/transactions", method="POST", data={
            "customer_id": cust_b["id"],
            "type": "credit",
            "amount": 1000,
            "note": "Hacked tx"
        }, token=token_a)
        assert status == 404, f"Expected 404 for creating cross-store transaction, got {status}"
        print("-> Blocked POST cross-store transaction.")

        # DELETE customer B from A's token
        status, err = request(f"/api/customers/{cust_b['id']}", method="DELETE", token=token_a)
        assert status == 404, f"Expected 404 for deleting cross-store customer, got {status}"
        print("-> Blocked DELETE cross-store customer.")
        print("-> DATA ISOLATION IS 100% SECURE.")

        # 5. Test Undo on Delete Transaction
        print("5. Testing Transaction Delete with Undo Payload...")
        # Add a valid transaction for customer A
        status, tx = request("/api/transactions", method="POST", data={
            "customer_id": cust_a["id"],
            "type": "credit",
            "amount": 5500,
            "note": "Biscuits"
        }, token=token_a)
        assert status == 201
        
        # Delete transaction and check response includes deleted_transaction details
        status, del_res = request(f"/api/transactions/{tx['id']}", method="DELETE", token=token_a)
        assert status == 200, f"Expected 200, got {status}"
        assert "deleted_transaction" in del_res, "Expected deleted_transaction payload for client-side undo"
        assert del_res["deleted_transaction"]["amount"] == 5500, "Deleted transaction amount mismatch"
        print("-> Transaction Delete Undo payload works.")

        # 6. Test Daily CLOSING Summary & CSV Export
        print("6. Testing daily closing summary & export...")
        # Log another transaction
        status, _ = request("/api/transactions", method="POST", data={
            "customer_id": cust_a["id"],
            "type": "credit",
            "amount": 12000,
            "note": "Rice sack"
        }, token=token_a)
        assert status == 201

        # GET today's summary
        status, today = request("/api/dashboard/today", token=token_a)
        assert status == 200
        assert today["total_credit_given"] == 12000, f"Expected 12000, got {today['total_credit_given']}"
        assert len(today["transactions"]) == 1, "Expected 1 transaction logged today"
        print("-> Today's closing summary OK.")

        # Export CSV
        url = f"{base_url}/api/export/transactions"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token_a}"})
        with urllib.request.urlopen(req) as res:
            csv_body = res.read().decode("utf-8")
            assert res.status == 200
            assert "Customer Name,Phone,Type,Amount (Rs),Note,Date" in csv_body, "CSV headers missing"
            assert "Customer A" in csv_body, "Customer A record missing from CSV"
            assert "120.00" in csv_body, "Amount in rupees formatting wrong"
        print("-> CSV Export OK.")

        # Export PDF
        url_pdf = f"{base_url}/api/export/pdf"
        req_pdf = urllib.request.Request(url_pdf, headers={"Authorization": f"Bearer {token_a}"})
        with urllib.request.urlopen(req_pdf) as res_pdf:
            pdf_bytes = res_pdf.read()
            assert res_pdf.status == 200
            assert len(pdf_bytes) > 100, "PDF response empty"
            assert pdf_bytes.startswith(b"%PDF"), "Response is not a valid PDF file"
        print("-> PDF Export OK.")

        # Test reminder link language and price itemization
        status, rem_te = request(f"/api/customers/{cust_a['id']}/reminder-link?lang=te", token=token_a)
        assert status == 200
        assert "నమస్తే" in rem_te["sms_text"]
        assert "Rice sack (₹120)" in rem_te["sms_text"]
        
        status, rem_en = request(f"/api/customers/{cust_a['id']}/reminder-link?lang=en", token=token_a)
        assert status == 200
        assert "Namaste" in rem_en["sms_text"]
        assert "Rice sack (₹120)" in rem_en["sms_text"]

        status, rem_hi = request(f"/api/customers/{cust_a['id']}/reminder-link?lang=hi", token=token_a)
        assert status == 200
        assert "नमस्ते" in rem_hi["sms_text"]
        assert "आज की खरीदारी: Rice sack (₹120)" in rem_hi["sms_text"]
        print("-> Translated & Itemized Reminder links (EN, TE, HI) OK.")

        # Test customer PDF export endpoints
        for r in ["today", "all"]:
            for l in ["en", "te", "hi"]:
                url_cpdf = f"{base_url}/api/customers/{cust_a['id']}/export/pdf?range={r}&lang={l}"
                req_cpdf = urllib.request.Request(url_cpdf, headers={"Authorization": f"Bearer {token_a}"})
                with urllib.request.urlopen(req_cpdf) as res_cpdf:
                    cpdf_bytes = res_cpdf.read()
                    assert res_cpdf.status == 200
                    assert len(cpdf_bytes) > 100, f"Customer PDF empty for range={r}, lang={l}"
                    assert cpdf_bytes.startswith(b"%PDF"), f"Customer PDF invalid header for range={r}, lang={l}"
        print("-> Customer Report PDF exports (Today & All in EN, TE, HI) OK.")

        # 7. Test Staff Logins & Last Owner Protection
        print("7. Testing staff login creation and owner-only checks...")
        # Create Staff User A (role: staff)
        status, staff = request("/api/users", method="POST", data={
            "name": "Staff A",
            "pin": "3333",
            "role": "staff",
            "recovery_question": "Pet?",
            "recovery_answer": "cat"
        }, token=token_a)
        assert status == 201, f"Expected 201, got {status}"
        staff_id = staff["id"]
        
        # Test Duplicate PIN within same store (should fail with 409)
        status, err = request("/api/users", method="POST", data={
            "name": "Staff Duplicate",
            "pin": "3333",
            "role": "staff"
        }, token=token_a)
        assert status == 409, f"Expected 409 conflict, got {status}"
        print("-> PIN duplicates within same store blocked correctly.")

        # Login as Staff A
        status, login_staff = request("/api/login", method="POST", data={
            "store_id": store_a_id,
            "pin": "3333"
        })
        assert status == 200
        token_staff = login_staff["token"]
        print("-> Staff A logged in successfully.")

        # Staff A tries to delete Owner A (should be blocked - 403)
        status, err = request(f"/api/users/{owner_a_id}", method="DELETE", token=token_staff)
        assert status == 403, f"Expected 403 for staff deleting user, got {status}"
        print("-> Staff blocked from deleting users.")

        # Owner A deletes Staff A (should succeed)
        status, res = request(f"/api/users/{staff_id}", method="DELETE", token=token_a)
        assert status == 200
        print("-> Owner deleted staff member successfully.")

        # Owner A tries to delete Owner A (blocked because last owner - 400)
        status, err = request(f"/api/users/{owner_a_id}", method="DELETE", token=token_a)
        assert status == 400, f"Expected 400 for deleting last owner, got {status}"
        assert err["detail"] == "Cannot delete the last remaining owner of this store.", f"Unexpected message: {err}"
        print("-> Last Owner protection holds.")

        # 8. Test PIN Recovery Flow
        print("8. Testing PIN reset question flow...")
        # Create user with recovery answer
        status, staff_rec = request("/api/users", method="POST", data={
            "name": "Staff Recovery",
            "pin": "5555",
            "role": "staff",
            "recovery_question": "Favorite food?",
            "recovery_answer": "biryani"
        }, token=token_a)
        assert status == 201
        staff_rec_id = staff_rec["id"]

        # Request recovery question
        status, reset_req = request("/api/pin-reset/request", method="POST", data={
            "store_id": store_a_id,
            "user_name": "Staff Recovery"
        })
        assert status == 200
        assert reset_req["recovery_question"] == "Favorite food?"

        # Confirm PIN reset with wrong answer (should fail 401)
        status, err = request("/api/pin-reset/confirm", method="POST", data={
            "store_id": store_a_id,
            "user_id": staff_rec_id,
            "recovery_answer": "pizza",
            "new_pin": "6666"
        })
        assert status == 401, f"Expected 401 for wrong reset answer, got {status}"

        # Confirm PIN reset with correct answer (should succeed 200)
        status, res = request("/api/pin-reset/confirm", method="POST", data={
            "store_id": store_a_id,
            "user_id": staff_rec_id,
            "recovery_answer": "biryani",
            "new_pin": "6666"
        })
        assert status == 200
        
        # Verify new PIN works for login
        status, login_new = request("/api/login", method="POST", data={
            "store_id": store_a_id,
            "pin": "6666"
        })
        assert status == 200, f"Expected 200 for new login, got {status}"
        print("-> PIN Recovery flow verified.")

        print("\n=== ALL MULTI-STORE TENANCY AND SECURITY TESTS PASSED! ===")

    finally:
        print("Stopping test server...")
        server_process.terminate()
        server_process.wait()
        print("Test server stopped.")

if __name__ == "__main__":
    run_tests()
