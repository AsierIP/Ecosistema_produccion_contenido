"""Local scheduler. No model calls or external effects in planning."""
from __future__ import annotations
from datetime import date, datetime
from .config import ROOT, load_channels, read_json, readiness
from .store import Store

def production_date(timezone="Europe/Madrid"):
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(timezone)).date().isoformat()
    except Exception as exc:
        if timezone == "Europe/Madrid":
            # Windows may omit the IANA database. EU rules: last Sunday March/October.
            from datetime import timezone as utc_zone, timedelta
            utc = datetime.now(utc_zone.utc)
            def last_sunday(month):
                end = date(utc.year, month + 1, 1) - timedelta(days=1)
                return end - timedelta(days=(end.weekday() + 1) % 7)
            start = datetime.combine(last_sunday(3), datetime.min.time(), utc_zone.utc) + timedelta(hours=1)
            end = datetime.combine(last_sunday(10), datetime.min.time(), utc_zone.utc) + timedelta(hours=1)
            return (utc + timedelta(hours=2 if start <= utc < end else 1)).date().isoformat()
        raise ValueError(f"Timezone unavailable: {timezone}") from exc

def plan_daily(root=ROOT, day=None):
    settings = read_json(root / "config/ecosystem.json")
    local_path = root / "local.json"
    local = read_json(local_path) if local_path.exists() else {}
    day = day or production_date(settings["timezone"])
    date.fromisoformat(day)
    results = []
    with Store(root / ".runtime/production.sqlite3") as store:
        for channel in load_channels(root):
            blockers = readiness(channel, local, settings)
            pending = [j for j in store.list_jobs(channel_id=channel["id"]) if j["state"] != "complete"]
            pending.sort(key=lambda j: j["production_date"])
            job = pending[0] if pending else store.enqueue_job(channel["id"], day, metadata={"name": channel["name"]})
            results.append({"channel_id": channel["id"], "name": channel["name"], "job_id": job["id"],
                            "production_date": job["production_date"], "state": job["state"], "ready": not blockers and job["state"] != "complete",
                            "blockers": blockers, "resuming": job["production_date"] != day})
    return {"date": day, "status": "READY" if any(r["ready"] for r in results) else "BLOCKED", "channels": results,
            "note": "Plan local; no equivale a producción ni publicación completada."}
