# ============================================================
#  Phoenix-SAKHI — FastAPI Backend v2.0 (Fixed)
# ============================================================

import os
import uuid
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

# ── Supabase ──────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY env var missing!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Models ────────────────────────────────────────────────
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

# ── Health check ──────────────────────────────────────────
@app.get("/")
def root():
    return {
        "message": "Phoenix-SAKHI API v2.0 running ✅",
        "status":  "online"
    }

# ── Register user ─────────────────────────────────────────
@app.post("/register")
def register_user(user: UserModel):
    try:
        supabase.table("users").upsert({
            "user_id":           user.user_id,
            "name":              user.name,
            "phone":             user.phone,
            "emergency_contact": user.emergency_contact,
            "emergency_phone":   user.emergency_phone,
            "address":           user.address,
            "photo_url":         user.photo_url,
        }).execute()
        return {"status": "registered", "user_id": user.user_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Get all users ─────────────────────────────────────────
@app.get("/users")
def get_users():
    try:
        res = supabase.table("users").select("*").execute()
        return res.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Create alert ──────────────────────────────────────────
@app.post("/alert")
def create_alert(alert: AlertModel):
    if alert.alert_type not in ["SOS_BUTTON", "SOS_FALL"]:
        raise HTTPException(status_code=400, detail="Invalid alert_type")
    try:
        alert_id = str(uuid.uuid4())
        supabase.table("alerts").insert({
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
        raise HTTPException(status_code=500, detail=str(e))

# ── Get all alerts ────────────────────────────────────────
@app.get("/alerts")
def get_alerts():
    try:
        res = supabase.table("alerts") \
            .select("*, users(name, phone, emergency_contact, emergency_phone, address)") \
            .order("timestamp", desc=True) \
            .execute()
        alerts = []
        for row in (res.data or []):
            flat = dict(row)
            if flat.get("users"):
                flat.update(flat.pop("users"))
            alerts.append(flat)
        return alerts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Get single alert ──────────────────────────────────────
@app.get("/alerts/{alert_id}")
def get_alert(alert_id: str):
    try:
        res = supabase.table("alerts") \
            .select("*, users(name, phone, emergency_contact, emergency_phone, address)") \
            .eq("id", alert_id).single().execute()
        flat = dict(res.data)
        if flat.get("users"):
            flat.update(flat.pop("users"))
        return flat
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

# ── Resolve alert ─────────────────────────────────────────
@app.put("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, body: ResolveModel):
    try:
        supabase.table("alerts").update({
            "status": "resolved",
            "notes":  body.notes
        }).eq("id", alert_id).execute()
        return {"status": "resolved", "alert_id": alert_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Delete alert ──────────────────────────────────────────
@app.delete("/alerts/{alert_id}")
def delete_alert(alert_id: str):
    try:
        supabase.table("alerts").delete().eq("id", alert_id).execute()
        return {"status": "deleted", "alert_id": alert_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Upload audio for an alert ─────────────────────────────
@app.post("/alerts/{alert_id}/audio")
async def upload_audio(alert_id: str, audio: UploadFile = File(...)):
    try:
        # Read file bytes
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file")

        filename = f"{alert_id}_{int(time.time())}.aac"

        # Upload to Supabase Storage bucket "recordings"
        supabase.storage.from_("recordings").upload(
            filename,
            audio_bytes,
            {"content-type": "audio/aac", "upsert": "true"}
        )

        # Get public URL
        public_url = supabase.storage.from_("recordings").get_public_url(filename)

        # Save URL to alert row
        supabase.table("alerts").update(
            {"audio_url": public_url}
        ).eq("id", alert_id).execute()

        return {
            "status":    "Audio uploaded",
            "alert_id":  alert_id,
            "audio_url": public_url
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio upload error: {str(e)}")

# ── Standalone audio upload (no alert id yet) ─────────────
@app.post("/audio/upload")
async def upload_audio_standalone(audio: UploadFile = File(...)):
    try:
        audio_bytes = await audio.read()
        filename    = f"standalone_{int(time.time())}.aac"
        supabase.storage.from_("recordings").upload(
            filename,
            audio_bytes,
            {"content-type": "audio/aac", "upsert": "true"}
        )
        public_url = supabase.storage.from_("recordings").get_public_url(filename)
        return {"status": "Uploaded", "audio_url": public_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Get audio URL for an alert ────────────────────────────
@app.get("/alerts/{alert_id}/audio")
def get_audio(alert_id: str):
    try:
        res = supabase.table("alerts") \
            .select("audio_url").eq("id", alert_id).single().execute()
        audio_url = (res.data or {}).get("audio_url")
        if not audio_url:
            raise HTTPException(status_code=404, detail="No audio for this alert")
        return {"alert_id": alert_id, "audio_url": audio_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

# ── Stats ─────────────────────────────────────────────────
@app.get("/stats")
def get_stats():
    try:
        alerts = supabase.table("alerts").select("status, alert_type, audio_url").execute().data or []
        users  = supabase.table("users").select("user_id", count="exact").execute()
        return {
            "total":      len(alerts),
            "active":     sum(1 for a in alerts if a.get("status")     == "active"),
            "resolved":   sum(1 for a in alerts if a.get("status")     == "resolved"),
            "sos_button": sum(1 for a in alerts if a.get("alert_type") == "SOS_BUTTON"),
            "sos_fall":   sum(1 for a in alerts if a.get("alert_type") == "SOS_FALL"),
            "with_audio": sum(1 for a in alerts if a.get("audio_url")),
            "users":      users.count or 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
