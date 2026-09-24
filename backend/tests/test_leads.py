async def test_create_lead_normalises_contact_details(admin_client, users):
    resp = await admin_client.post("/api/leads", json={
        "name": "  Ananya   Iyer ", "email": "Ananya@Example.COM", "phone": "98123 45670", "lead_source": "Webinar",
        "sales_person_id": str(users["sales"]["_id"]),
    })
    assert resp.status_code == 201, resp.text
    lead = resp.json()
    assert lead["name"] == "Ananya Iyer"
    assert lead["email"] == "ananya@example.com"
    assert lead["phone"] == "+919812345670"
    assert lead["sales_person"]["id"] == str(users["sales"]["_id"])
    assert lead["lead_status"] == "new"


async def test_create_lead_validation_errors(admin_client, users, db):
    resp = await admin_client.post("/api/leads", json={
        "name": "X", "email": "not-an-email", "phone": "12", "sales_person_id": str(users["sales"]["_id"]),
    })
    assert resp.status_code == 422
    fields = {f["field"] for f in resp.json()["error"]["details"]["fields"]}
    assert {"name", "email", "phone"} <= fields


async def test_create_lead_requires_a_sales_person(admin_client):
    resp = await admin_client.post("/api/leads", json={"name": "Someone", "email": "someone@example.com", "phone": "+919000000009"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_sales_person"


async def test_sales_cannot_create_or_edit_or_delete_leads(sales_client, lead):
    resp = await sales_client.post("/api/leads", json={"name": "New", "email": "new2@example.com", "phone": "+919000000002"})
    assert resp.status_code == 403
    resp = await sales_client.put(f"/api/leads/{lead['id']}", json={"company": "New Co"})
    assert resp.status_code == 403
    resp = await sales_client.delete(f"/api/leads/{lead['id']}")
    assert resp.status_code == 403


async def test_duplicate_lead_rejected(admin_client, lead, users):
    resp = await admin_client.post("/api/leads", json={
        "name": "Someone", "email": "RAHUL@example.com", "phone": "+919000000001", "sales_person_id": str(users["sales"]["_id"]),
    })
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "duplicate_lead"
    resp = await admin_client.post("/api/leads", json={
        "name": "Someone", "email": "new@example.com", "phone": "+91 98765 43210", "sales_person_id": str(users["sales"]["_id"]),
    })
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["field"] == "phone"


async def test_sales_person_cannot_access_other_leads(other_client, lead):
    resp = await other_client.get(f"/api/leads/{lead['id']}")
    assert resp.status_code == 403
    listing = await other_client.get("/api/leads")
    assert listing.json()["total"] == 0


async def test_admin_sees_all_and_can_reassign(admin_client, lead, users):
    listing = await admin_client.get("/api/leads")
    assert listing.json()["total"] == 1
    resp = await admin_client.put(f"/api/leads/{lead['id']}", json={"sales_person_id": str(users["other"]["_id"])})
    assert resp.status_code == 200
    assert resp.json()["sales_person"]["id"] == str(users["other"]["_id"])


async def test_lead_search_filter(sales_client, lead):
    resp = await sales_client.get("/api/leads", params={"q": "rahul"})
    assert resp.json()["total"] == 1
    resp = await sales_client.get("/api/leads", params={"q": "43210"})
    assert resp.json()["total"] == 1
    resp = await sales_client.get("/api/leads", params={"q": "nobody"})
    assert resp.json()["total"] == 0


async def test_admin_edits_lead(admin_client, lead):
    resp = await admin_client.put(f"/api/leads/{lead['id']}", json={"company": "New Co"})
    assert resp.json()["company"] == "New Co"


async def test_lead_export_csv(sales_client, lead):
    resp = await sales_client.get("/api/leads/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("Name,Email,Phone")
    assert "rahul@example.com" in lines[1]
    assert "+919876543210" in lines[1]


async def test_requires_authentication(anon_client):
    resp = await anon_client.get("/api/leads")
    assert resp.status_code == 401
