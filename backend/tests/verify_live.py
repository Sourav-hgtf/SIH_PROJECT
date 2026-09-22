import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_live_system():
    print("=== LIVE SYSTEM VERIFICATION ===")
    
    # 1. Health check
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200, f"Health check failed: {r.text}"
    print("[PASS] Health Check OK")
    
    # 2. Test Admin Login via /v1/auth/login
    r = requests.post(
        f"{BASE_URL}/v1/auth/login",
        json={"username": "admin", "password": "admin123"}
    )
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    admin_auth = r.json()
    token = admin_auth["access_token"]
    print(f"[PASS] Admin Logged in successfully: {admin_auth['username']} (Role: {admin_auth['role']})")
    
    # 3. Test /v1/auth/me
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}/v1/auth/me", headers=headers)
    assert r.status_code == 200, f"Get /me failed: {r.text}"
    me_data = r.json()
    print(f"[PASS] /v1/auth/me returned: user={me_data['username']}, scopes={me_data['site_scope']}, email={me_data['email']}")
    
    # 4. Test Listing Users via /v1/admin/users
    r = requests.get(f"{BASE_URL}/v1/admin/users", headers=headers)
    assert r.status_code == 200, f"Get users failed: {r.text}"
    users = r.json()
    print(f"[PASS] Listed {len(users)} users successfully:")
    for u in users:
        print(f"       • {u['username']:<18} | Role: {u['role']:<14} | Active: {str(u['is_active']):<6} | Scopes: {u['site_scope']}")
    
    # 5. Test User Editing (Update email and site scopes for analyst_field)
    analyst_user = next((u for u in users if u["username"] == "analyst_field"), None)
    if analyst_user:
        user_id = analyst_user["id"]
        update_payload = {
            "email": "field.analyst.updated@oilindia.in",
            "site_scope": ["MORAN_FIELD", "JORHAT_FIELD", "BAGHJAN_OILFIELD", "DULIAJAN_GCS"]
        }
        r = requests.patch(f"{BASE_URL}/v1/admin/users/{user_id}", json=update_payload, headers=headers)
        assert r.status_code == 200, f"User update failed: {r.text}"
        updated = r.json()
        print(f"[PASS] Successfully updated analyst_field scopes: {updated['site_scope']}")
        
        # Toggle active status test (deactivate)
        r = requests.post(f"{BASE_URL}/v1/admin/users/{user_id}/toggle-active", json={"is_active": False}, headers=headers)
        assert r.status_code == 200, f"Toggle active false failed: {r.text}"
        print(f"[PASS] Toggled active status for {analyst_user['username']} -> is_active = {r.json()['is_active']}")
        
        # Toggle back to active (reactivate)
        r = requests.post(f"{BASE_URL}/v1/admin/users/{user_id}/toggle-active", json={"is_active": True}, headers=headers)
        assert r.status_code == 200, f"Toggle active true failed: {r.text}"
        print(f"[PASS] Restored active status for {analyst_user['username']} -> is_active = {r.json()['is_active']}")

    # 6. Test Self-Deactivation Guard (Admin attempting to deactivate themselves)
    admin_user = next(u for u in users if u["username"] == "admin")
    r = requests.post(f"{BASE_URL}/v1/admin/users/{admin_user['id']}/toggle-active", json={"is_active": False}, headers=headers)
    assert r.status_code == 400, "Self-deactivation guard failed!"
    print(f"[PASS] Self-deactivation guard properly rejected with 400: {r.json()['detail']}")

    # 7. Test Audit Logs
    r = requests.get(f"{BASE_URL}/v1/admin/audit-log", headers=headers)
    assert r.status_code == 200, f"Get audit log failed: {r.text}"
    logs = r.json()
    print(f"[PASS] Retrieved {len(logs)} audit logs successfully.")
    for l in logs[:3]:
        print(f"       • Action: {l['action_type']:<22} | Entity: {l.get('entity_type')}:{l.get('entity_id')} | Created: {l['created_at']}")

    # 8. Test Non-Admin Rejection (Analyst attempting to access /v1/admin/users)
    r_analyst = requests.post(
        f"{BASE_URL}/v1/auth/login",
        json={"username": "analyst", "password": "analyst123"}
    )
    assert r_analyst.status_code == 200
    analyst_token = r_analyst.json()["access_token"]
    r_forbidden = requests.get(f"{BASE_URL}/v1/admin/users", headers={"Authorization": f"Bearer {analyst_token}"})
    assert r_forbidden.status_code == 403, f"Non-admin access was not blocked: {r_forbidden.status_code}"
    print(f"[PASS] Non-admin access properly blocked with 403 Forbidden: {r_forbidden.json()['detail']}")

    # 9. Test Site Manager & Leadership Logins
    for test_user, test_pass, expected_role in [
        ("manager_digboi", "manager123", "site_manager"),
        ("manager_moran", "manager123", "site_manager"),
        ("manager_jorhat", "manager123", "site_manager"),
        ("manager_baghjan", "manager123", "site_manager"),
        ("leadership", "leader123", "leadership"),
    ]:
        r_test = requests.post(f"{BASE_URL}/v1/auth/login", json={"username": test_user, "password": test_pass})
        assert r_test.status_code == 200, f"Login failed for {test_user}"
        res_json = r_test.json()
        assert res_json["role"] == expected_role
        print(f"[PASS] Login verified for {test_user} -> role={res_json['role']}")

    print("\n==========================================")
    print("ALL 9 LIVE VERIFICATION CHECKS PASSED 100%!")
    print("==========================================")

if __name__ == "__main__":
    test_live_system()
