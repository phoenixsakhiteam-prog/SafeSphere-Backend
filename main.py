# ============================================================
#  Phoenix-SAKHI — FastAPI Backend v2.0
#  New: POST /alerts/{id}/audio  — upload recorded audio
#  New: GET  /alerts/{id}/audio  — get audio URL
# ============================================================

import os, uuid, time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Phoenix-SAKHI API v2", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Supabase client ───────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Pydantic models ───────────────────────────────────────
class UserModel(BaseModel):
    user_id:           str
    name:              str
    phone:             str
    emergency_contact: Optional[str] = ""
    emergency_phone:   Optional[str] = ""
    address:           Optional[str] = ""
    photo_url:         Optional[str] = ""

class AlertModel(BaseModel):
    user_id:    str
    alert_type: str
    latitude:   float
    longitude:  float

class ResolveModel(BaseModel):
    notes: Optional[str] = ""

# ─────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "Phoenix-SAKHI API v2.0 ✅", "status": "running",
            "endpoints": ["/register", "/users", "/alert", "/alerts",
                          "/alerts/{id}", "/alerts/{id}/resolve",
                          "/alerts/{id}/audio", "/stats"]}

# ── User registration ─────────────────────────────────────
@app.post("/register")
def register_user(user: UserModel):
    try:
        res = supabase.table("users").upsert({
            "user_id":           user.user_id,
            "name":              user.name,
            "phone":             user.phone,
            "emergency_contact": user.emergency_contact,
            "emergency_phone":   user.emergency_phone,
            "address":           user.address,
            "photo_url":         user.photo_url,
        }).execute()
        return {"status": "User registered", "user_id": user.user_id}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Get all users ─────────────────────────────────────────
@app.get("/users")
def get_users():
    try:
        res = supabase.table("users").select("*").execute()
        return res.data or []
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Create SOS alert ─────────────────────────────────────
@app.post("/alert")
def create_alert(alert: AlertModel):
    if alert.alert_type not in ["SOS_BUTTON", "SOS_FALL"]:
        raise HTTPException(400, "alert_type must be SOS_BUTTON or SOS_FALL")
    try:
        alert_id = str(uuid.uuid4())
        res = supabase.table("alerts").insert({
            "id":         alert_id,
            "user_id":    alert.user_id,
            "alert_type": alert.alert_type,
            "latitude":   alert.latitude,
            "longitude":  alert.longitude,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "status":     "active",
        }).execute()
        return {"status": "Alert created", "alert_id": alert_id}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Get all alerts ────────────────────────────────────────
@app.get("/alerts")
def get_alerts():
    try:
        res = supabase.table("alerts")\
            .select("*, users(name,phone,emergency_contact,emergency_phone,address)")\
            .order("timestamp", desc=True).execute()
        alerts = []
        for row in (res.data or []):
            flat = dict(row)
            if flat.get("users"):
                flat.update(flat.pop("users"))
            alerts.append(flat)
        return alerts
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Get single alert ──────────────────────────────────────
@app.get("/alerts/{alert_id}")
def get_alert(alert_id: str):
    try:
        res = supabase.table("alerts")\
            .select("*, users(name,phone,emergency_contact,emergency_phone,address)")\
            .eq("id", alert_id).single().execute()
        flat = dict(res.data)
        if flat.get("users"):
            flat.update(flat.pop("users"))
        return flat
    except Exception as e:
        raise HTTPException(404, f"Alert not found: {e}")

# ── Resolve alert ─────────────────────────────────────────
@app.put("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, body: ResolveModel):
    try:
        supabase.table("alerts").update({
            "status": "resolved",
            "notes":  body.notes
        }).eq("id", alert_id).execute()
        return {"status": "Alert resolved", "alert_id": alert_id}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Delete alert ──────────────────────────────────────────
@app.delete("/alerts/{alert_id}")
def delete_alert(alert_id: str):
    try:
        supabase.table("alerts").delete().eq("id", alert_id).execute()
        return {"status": "Alert deleted", "alert_id": alert_id}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── AUDIO UPLOAD ──────────────────────────────────────────
@app.post("/alerts/{alert_id}/audio")
async def upload_audio(alert_id: str, audio: UploadFile = File(...)):
    """
    Receives audio recording from Android app,
    stores in Supabase Storage bucket 'recordings',
    updates alert row with audio_url.
    """
    try:
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(400, "Empty audio file")

        filename = f"{alert_id}_{int(time.time())}.aac"

        # Upload to Supabase Storage bucket "recordings"
        upload_res = supabase.storage.from_("recordings").upload(
            filename,
            audio_bytes,
            {"content-type": "audio/aac", "upsert": "true"}
        )

        # Get public URL
        public_url = supabase.storage.from_("recordings").get_public_url(filename)

        # Update alert with audio_url
        supabase.table("alerts").update({
            "audio_url": public_url
        }).eq("id", alert_id).execute()

        return {
            "status":    "Audio uploaded",
            "alert_id":  alert_id,
            "audio_url": public_url,
            "filename":  filename
        }
    except Exception as e:
        raise HTTPException(500, f"Audio upload failed: {e}")

# ── GET audio URL for an alert ────────────────────────────
@app.get("/alerts/{alert_id}/audio")
def get_audio(alert_id: str):
    try:
        res = supabase.table("alerts")\
            .select("audio_url").eq("id", alert_id).single().execute()
        audio_url = res.data.get("audio_url")
        if not audio_url:
            raise HTTPException(404, "No audio for this alert")
        return {"alert_id": alert_id, "audio_url": audio_url}
    except Exception as e:
        raise HTTPException(404, str(e))

# ── Standalone audio upload (no alert_id) ─────────────────
@app.post("/audio/upload")
async def upload_audio_standalone(audio: UploadFile = File(...)):
    """Fallback when alert_id is unknown at time of upload."""
    try:
        audio_bytes = await audio.read()
        filename = f"standalone_{int(time.time())}.aac"
        supabase.storage.from_("recordings").upload(
            filename, audio_bytes,
            {"content-type": "audio/aac", "upsert": "true"}
        )
        public_url = supabase.storage.from_("recordings").get_public_url(filename)
        return {"status": "Uploaded", "audio_url": public_url}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Stats ─────────────────────────────────────────────────
@app.get("/stats")
def get_stats():
    try:
        alerts = supabase.table("alerts").select("status,alert_type").execute().data or []
        users  = supabase.table("users").select("user_id", count="exact").execute()
        return {
            "total":    len(alerts),
            "active":   sum(1 for a in alerts if a["status"] == "active"),
            "resolved": sum(1 for a in alerts if a["status"] == "resolved"),
            "sos_button": sum(1 for a in alerts if a["alert_type"] == "SOS_BUTTON"),
            "sos_fall":   sum(1 for a in alerts if a["alert_type"] == "SOS_FALL"),
            "users":    users.count or 0,
        }
    except Exception as e:
        raise HTTPException(500, str(e))
