# ============================================================
#  SafeSphere AI Guardian — Backend Server (Supabase Edition)
#  Stack : Python + FastAPI + Supabase (PostgreSQL)
#  Run   : uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# ============================================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv
import os
import datetime
import uvicorn

# ── Load .env ────────────────────────────────────────────────
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")   # use service role for backend

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── App ──────────────────────────────────────────────────────
app = FastAPI(title="SafeSphere API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restrict to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ────────────────────────────────────────────────────────────
#  PYDANTIC MODELS
# ────────────────────────────────────────────────────────────
class AlertRequest(BaseModel):
    user_id:    str
    alert_type: str          # "SOS_BUTTON" or "SOS_FALL"
    latitude:   float
    longitude:  float

class UserRegister(BaseModel):
    user_id:           str
    name:              str
    phone:             str
    emergency_contact: Optional[str] = None
    emergency_phone:   Optional[str] = None
    address:           Optional[str] = None

class ResolveRequest(BaseModel):
    notes: Optional[str] = None

# ────────────────────────────────────────────────────────────
#  ROUTES
# ────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"message": "SafeSphere API v2.0 running ✅ (Supabase)"}


# ── Register User ────────────────────────────────────────────
@app.post("/register", tags=["Users"])
def register_user(user: UserRegister):
    data = {
        "user_id":           user.user_id,
        "name":              user.name,
        "phone":             user.phone,
        "emergency_contact": user.emergency_contact,
        "emergency_phone":   user.emergency_phone,
        "address":           user.address,
    }
    # upsert so re-registration updates existing record
    res = supabase.table("users").upsert(data, on_conflict="user_id").execute()
    if res.data:
        return {"status": "success", "message": f"User '{user.name}' registered."}
    raise HTTPException(status_code=500, detail="Failed to register user.")


# ── Get All Users ────────────────────────────────────────────
@app.get("/users", tags=["Users"])
def get_users():
    res = supabase.table("users").select("*").execute()
    return res.data or []


# ── Send Alert (Android App calls this) ─────────────────────
@app.post("/alert", tags=["Alerts"])
def send_alert(alert: AlertRequest):
    # Verify user exists
    user_res = supabase.table("users") \
        .select("user_id") \
        .eq("user_id", alert.user_id) \
        .execute()
    if not user_res.data:
        raise HTTPException(status_code=404, detail="User not registered.")

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data = {
        "user_id":    alert.user_id,
        "alert_type": alert.alert_type,
        "latitude":   alert.latitude,
        "longitude":  alert.longitude,
        "timestamp":  timestamp,
        "status":     "active",
    }
    res = supabase.table("alerts").insert(data).execute()
    if res.data:
        return {
            "status":    "success",
            "alert_id":  res.data[0]["id"],
            "timestamp": timestamp,
            "message":   "🚨 Alert received and logged."
        }
    raise HTTPException(status_code=500, detail="Failed to log alert.")


# ── Get All Alerts ───────────────────────────────────────────
@app.get("/alerts", tags=["Alerts"])
def get_alerts(status: Optional[str] = None):
    query = supabase.table("alerts") \
        .select("*, users(name, phone, emergency_contact, emergency_phone, address)") \
        .order("timestamp", desc=True)
    if status:
        query = query.eq("status", status)
    res = query.execute()
    # Flatten nested users object
    result = []
    for row in (res.data or []):
        flat = {**row}
        if flat.get("users"):
            flat.update(flat.pop("users"))
        result.append(flat)
    return result


# ── Get Single Alert ─────────────────────────────────────────
@app.get("/alerts/{alert_id}", tags=["Alerts"])
def get_alert(alert_id: str):
    res = supabase.table("alerts") \
        .select("*, users(name, phone, emergency_contact, emergency_phone, address)") \
        .eq("id", alert_id) \
        .single() \
        .execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Alert not found.")
    flat = {**res.data}
    if flat.get("users"):
        flat.update(flat.pop("users"))
    return flat


# ── Resolve Alert ─────────────────────────────────────────────
@app.put("/alerts/{alert_id}/resolve", tags=["Alerts"])
def resolve_alert(alert_id: str, body: ResolveRequest = ResolveRequest()):
    res = supabase.table("alerts") \
        .update({"status": "resolved", "notes": body.notes}) \
        .eq("id", alert_id) \
        .execute()
    if res.data:
        return {"status": "success", "message": f"Alert {alert_id} resolved."}
    raise HTTPException(status_code=500, detail="Failed to resolve.")


# ── Delete Alert ──────────────────────────────────────────────
@app.delete("/alerts/{alert_id}", tags=["Alerts"])
def delete_alert(alert_id: str):
    supabase.table("alerts").delete().eq("id", alert_id).execute()
    return {"status": "success", "message": f"Alert {alert_id} deleted."}


# ── Stats ─────────────────────────────────────────────────────
@app.get("/stats", tags=["Dashboard"])
def get_stats():
    alerts_res = supabase.table("alerts").select("status, alert_type").execute()
    users_res  = supabase.table("users").select("user_id", count="exact").execute()
    rows = alerts_res.data or []
    return {
        "total_alerts":  len(rows),
        "active_alerts": sum(1 for r in rows if r["status"]     == "active"),
        "resolved":      sum(1 for r in rows if r["status"]     == "resolved"),
        "total_users":   users_res.count or 0,
        "sos_button":    sum(1 for r in rows if r["alert_type"] == "SOS_BUTTON"),
        "sos_fall":      sum(1 for r in rows if r["alert_type"] == "SOS_FALL"),
    }


# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
