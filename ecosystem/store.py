"""SQLite orchestration state with CAS transitions and durable external intents.

Only one job exists per channel and production date. A network operation must be
prepared, then started with its current version before making the external call.
If its result is uncertain, reconcile it; never start it again speculatively.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid

from .quality import validate_qa, validate_publications, validate_publication_receipt

STAGES = ("queued", "script", "assets", "render", "qa", "publish", "complete")
STATES = ("queued", "running", "blocked", "failed", "complete")
RESOURCES = ("gpu", "remote")
_NAMESPACE = uuid.UUID("1b7a645e-dc97-4e46-8de9-c3f29cb4eae0")


class StoreError(RuntimeError):
    """Base orchestration error."""


class ConflictError(StoreError):
    """A stale version, incompatible retry or ownership conflict."""


class IntentUncertainError(ConflictError):
    """Reconciliation is required before any further external attempt."""


class QualityError(StoreError):
    """A terminal completion request lacks sufficient validated evidence."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonempty, trimmed string")
    return value


def _clock(now=None):
    value = time.time() if now is None else now
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("timestamp must be finite")
    return float(value)


class Store:
    """A connection-scoped durable store; use separate instances across threads.

    The database directory is created when needed. WAL and immediate transactions
    serialize competing claims without relying on in-memory scheduler locks.
    """

    def __init__(self, db_path):
        self.path = str(db_path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, isolation_level=None, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=30000")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, production_date TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'queued', state TEXT NOT NULL DEFAULT 'queued',
                version INTEGER NOT NULL DEFAULT 0, metadata TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                UNIQUE(channel_id, production_date)
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT REFERENCES jobs(id),
                kind TEXT NOT NULL, data TEXT NOT NULL, created_at REAL NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
                BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
            CREATE TABLE IF NOT EXISTS leases (
                resource TEXT PRIMARY KEY, owner TEXT NOT NULL, token TEXT NOT NULL,
                expires_at REAL NOT NULL, acquired_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS intents (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                platform TEXT NOT NULL, action TEXT NOT NULL, master_sha256 TEXT NOT NULL,
                payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'prepared',
                version INTEGER NOT NULL DEFAULT 0, evidence TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                UNIQUE(job_id, platform, action)
            );
        """)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        """Release this database connection."""
        self.connection.close()

    @contextmanager
    def _transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    @staticmethod
    def _row(row):
        if row is None:
            return None
        result = dict(row)
        for key in ("metadata", "payload", "evidence", "data"):
            if key in result:
                result[key] = json.loads(result[key])
        return result

    def _event(self, job_id, kind, data, now=None):
        self.connection.execute(
            "INSERT INTO events(job_id,kind,data,created_at) VALUES(?,?,?,?)",
            (job_id, kind, _json(data), _clock(now)),
        )

    def enqueue_job(self, channel_id, production_date, metadata=None):
        """Idempotently create one job per channel/date; preserve original metadata."""
        _text(channel_id, "channel_id")
        _text(production_date, "production_date")
        if date.fromisoformat(production_date).isoformat() != production_date:
            raise ValueError("production_date must use YYYY-MM-DD")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        job_id = str(uuid.uuid5(_NAMESPACE, _json([channel_id, production_date])))
        now = _clock()
        with self._transaction():
            cursor = self.connection.execute(
                "INSERT OR IGNORE INTO jobs(id,channel_id,production_date,metadata,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (job_id, channel_id, production_date, _json(metadata or {}), now, now),
            )
            if cursor.rowcount:
                self._event(job_id, "job_created", {"channel_id": channel_id, "production_date": production_date}, now)
            return self.get_job(job_id)

    def get_job(self, job_id):
        """Return a decoded job or None."""
        return self._row(self.connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def list_jobs(self, channel_id=None, state=None):
        """List jobs in deterministic production-date and channel order."""
        conditions, values = [], []
        for field, value in (("channel_id", channel_id), ("state", state)):
            if value is not None:
                conditions.append(f"{field}=?")
                values.append(value)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return [self._row(row) for row in self.connection.execute(
            "SELECT * FROM jobs" + where + " ORDER BY production_date,channel_id", values
        )]

    def list_events(self, job_id=None):
        """Read the immutable event ledger in append order."""
        query, parameters = "SELECT * FROM events", ()
        if job_id is not None:
            query += " WHERE job_id=?"
            parameters = (job_id,)
        return [self._row(row) for row in self.connection.execute(query + " ORDER BY sequence", parameters)]

    def _transition(self, job_id, expected_version, stage, state, details, completion=False):
        if stage not in STAGES or state not in STATES:
            raise ValueError("unknown job stage or state")
        if not completion and (stage == "complete" or state == "complete"):
            raise QualityError("Use complete_job with QA and both public verification receipts")
        current = self.get_job(job_id)
        if current is None:
            raise KeyError(job_id)
        if current["version"] != expected_version or current["state"] == "complete":
            raise ConflictError("job version changed or job is already complete")
        if STAGES.index(stage) < STAGES.index(current["stage"]):
            if current["state"] not in ("failed", "blocked") or not details:
                raise ConflictError("backward stage transitions require blocked/failed state and recovery details")
        self.connection.execute(
            "UPDATE jobs SET stage=?,state=?,version=version+1,updated_at=? WHERE id=? AND version=?",
            (stage, state, _clock(), job_id, expected_version),
        )
        self._event(job_id, "job_transition", {
            "from_stage": current["stage"], "from_state": current["state"],
            "stage": stage, "state": state, "version": expected_version + 1,
            "details": details or {},
        })
        return self.get_job(job_id)

    def transition_job(self, job_id, expected_version, stage, state, details=None):
        """Change stage/state atomically using the version last read by the caller."""
        with self._transaction():
            return self._transition(job_id, expected_version, stage, state, details)

    def claim_lease(self, resource, owner, ttl_seconds, now=None):
        """Claim global gpu/remote capacity; return fenced lease or None if busy.

        Expired claims receive a new token, even for the same owner. Workers must
        renew while working and stop if renewal fails; a lease cannot stop an OS
        process by itself. now is injectable for deterministic clock tests.
        """
        if resource not in RESOURCES:
            raise ValueError("resource must be gpu or remote")
        _text(owner, "owner")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) or not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be finite and positive")
        now = _clock(now)
        with self._transaction():
            lease = self.connection.execute("SELECT * FROM leases WHERE resource=?", (resource,)).fetchone()
            if lease is not None and lease["expires_at"] > now:
                return None
            token = str(uuid.uuid4())
            self.connection.execute(
                "INSERT INTO leases(resource,owner,token,expires_at,acquired_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(resource) DO UPDATE SET owner=excluded.owner,token=excluded.token,expires_at=excluded.expires_at,acquired_at=excluded.acquired_at",
                (resource, owner, token, now + ttl_seconds, now),
            )
            self._event(None, "lease_claimed", {"resource": resource, "owner": owner, "token": token}, now)
            return dict(self.connection.execute("SELECT * FROM leases WHERE resource=?", (resource,)).fetchone())

    def renew_lease(self, resource, owner, token, ttl_seconds, now=None):
        """Extend an unexpired owned lease; return False after expiry or takeover."""
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) or not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be finite and positive")
        now = _clock(now)
        with self._transaction():
            changed = self.connection.execute(
                "UPDATE leases SET expires_at=? WHERE resource=? AND owner=? AND token=? AND expires_at>?",
                (now + ttl_seconds, resource, owner, token, now),
            ).rowcount
            if changed:
                self._event(None, "lease_renewed", {"resource": resource, "owner": owner, "token": token}, now)
            return bool(changed)

    def release_lease(self, resource, owner, token):
        """Release only the matching ownership token; a stale worker cannot unlock."""
        with self._transaction():
            changed = self.connection.execute(
                "DELETE FROM leases WHERE resource=? AND owner=? AND token=?", (resource, owner, token)
            ).rowcount
            if changed:
                self._event(None, "lease_released", {"resource": resource, "owner": owner, "token": token})
            return bool(changed)

    def get_intent(self, intent_id):
        """Read a durable external intent or None."""
        return self._row(self.connection.execute("SELECT * FROM intents WHERE id=?", (intent_id,)).fetchone())

    def list_intents(self, job_id=None):
        """Read external intents; sending and uncertain require reconciliation."""
        query, parameters = "SELECT * FROM intents", ()
        if job_id is not None:
            query += " WHERE job_id=?"
            parameters = (job_id,)
        return [self._row(row) for row in self.connection.execute(query + " ORDER BY created_at,id", parameters)]

    def prepare_intent(self, job_id, platform, action, master_sha256, payload=None):
        """Reserve a stable job/platform/action intent without making any call.

        Retry identical prepared intents. Verified intents return their receipt and
        must be skipped. sending/uncertain intents raise until reconciliation.
        Changing the master or payload of an existing intent is forbidden.
        """
        from .quality import SHA256_PATTERN, PLATFORMS
        if platform not in PLATFORMS:
            raise ValueError("unsupported platform")
        _text(action, "action")
        if not isinstance(master_sha256, str) or not SHA256_PATTERN.fullmatch(master_sha256):
            raise ValueError("master_sha256 must be a lowercase SHA-256")
        if payload is not None and not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        payload_json = _json(payload or {})
        intent_id = str(uuid.uuid5(_NAMESPACE, _json([job_id, platform, action])))
        now = _clock()
        with self._transaction():
            job = self.get_job(job_id)
            if job is None:
                raise KeyError(job_id)
            existing = self.get_intent(intent_id)
            if existing is not None:
                if existing["master_sha256"] != master_sha256 or _json(existing["payload"]) != payload_json:
                    raise ConflictError("existing intent has a different master or request payload")
                if existing["state"] in ("sending", "uncertain"):
                    raise IntentUncertainError("existing external operation must be reconciled before retry")
                return existing
            if job["state"] == "complete":
                raise ConflictError("completed jobs cannot create more external operations")
            if self.connection.execute(
                "SELECT 1 FROM intents WHERE job_id=? AND platform=? AND action='publish' AND state='verified'",
                (job_id, platform),
            ).fetchone():
                raise ConflictError("this platform already has a verified publication")
            self.connection.execute(
                "INSERT INTO intents(id,job_id,platform,action,master_sha256,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (intent_id, job_id, platform, action, master_sha256, payload_json, now, now),
            )
            self._event(job_id, "intent_prepared", {"intent_id": intent_id, "platform": platform, "action": action}, now)
            return self.get_intent(intent_id)

    def _change_intent(self, intent_id, expected_version, allowed_states, state, evidence):
        current = self.get_intent(intent_id)
        if current is None:
            raise KeyError(intent_id)
        if current["version"] != expected_version:
            raise ConflictError("intent version changed")
        if current["state"] not in allowed_states:
            if current["state"] in ("sending", "uncertain"):
                raise IntentUncertainError("external result must be reconciled before retry")
            raise ConflictError(f"cannot move intent from {current['state']} to {state}")
        self.connection.execute(
            "UPDATE intents SET state=?,version=version+1,evidence=?,updated_at=? WHERE id=? AND version=?",
            (state, _json(evidence), _clock(), intent_id, expected_version),
        )
        self._event(current["job_id"], "intent_" + state, {"intent_id": intent_id, "evidence": evidence, "version": expected_version + 1})
        return self.get_intent(intent_id)

    def start_intent(self, intent_id, expected_version):
        """CAS-claim exactly one external attempt; persist before issuing the call."""
        with self._transaction():
            current = self.get_intent(intent_id)
            if current is None:
                raise KeyError(intent_id)
            if self.connection.execute(
                "SELECT 1 FROM intents WHERE job_id=? AND platform=? AND action='publish' AND state='verified'",
                (current["job_id"], current["platform"]),
            ).fetchone():
                raise ConflictError("this platform already has a verified publication")
            return self._change_intent(intent_id, expected_version, ("prepared",), "sending", {})

    def mark_intent_uncertain(self, intent_id, expected_version, evidence):
        """Record timeout/ambiguous outcome; only reconciliation may allow a retry."""
        if not evidence:
            raise ValueError("uncertain outcome requires evidence")
        with self._transaction():
            return self._change_intent(intent_id, expected_version, ("sending",), "uncertain", evidence)

    def reconcile_intent(self, intent_id, expected_version, outcome, evidence):
        """Resolve sending/uncertain to verified or prepared after proven not_found.

        A publish verification requires a complete public receipt. not_found needs
        checked=True and nonempty evidence from an authoritative remote lookup;
        a timeout or transport failure is not evidence of absence.
        """
        if outcome not in ("verified", "not_found"):
            raise ValueError("outcome must be verified or not_found")
        if not isinstance(evidence, dict) or not evidence:
            raise ValueError("structured reconciliation evidence is required")
        with self._transaction():
            current = self.get_intent(intent_id)
            if current is None:
                raise KeyError(intent_id)
            if outcome == "not_found":
                if evidence.get("checked") is not True or not evidence.get("evidence"):
                    raise ValueError("retry requires checked absence and lookup evidence")
            elif current['platform'] == 'youtube' and current['action'] == 'schedule':
                from .release import validate_schedule_receipt
                errors = validate_schedule_receipt(evidence, current)
                if errors:
                    raise QualityError('; '.join(errors))
            elif current["action"] == "publish":
                account = current["payload"].get("expected_account_id")
                errors = validate_publication_receipt(evidence, current["platform"], current["master_sha256"], account)
                if errors:
                    raise QualityError("; ".join(errors))
            elif evidence.get("master_sha256") != current["master_sha256"] or not evidence.get("evidence"):
                raise QualityError("verified operation requires evidence bound to its master")
            return self._change_intent(
                intent_id, expected_version, ("sending", "uncertain"),
                "verified" if outcome == "verified" else "prepared", evidence,
            )

    def complete_job(self, job_id, expected_version, qa_package, publications, master_path, expected_accounts, profile=None, *, platforms=('youtube', 'tiktok')):
        """Complete only after real-master QA and both durable public verifications."""
        errors = validate_qa(qa_package, master_path, profile)
        errors.extend(validate_publications(publications, master_path, expected_accounts, platforms))
        if errors:
            raise QualityError("; ".join(errors))
        with self._transaction():
            intents = {intent["platform"]: intent for intent in self.list_intents(job_id) if intent["action"] == "publish"}
            for platform in platforms:
                intent = intents.get(platform)
                if intent is None or intent["state"] != "verified":
                    raise QualityError(f"{platform}: a verified durable publication intent is required")
                if intent["master_sha256"] != qa_package["master_sha256"] or intent["evidence"] != publications[platform]:
                    raise QualityError(f"{platform}: public receipt differs from the durable verified intent")
            return self._transition(job_id, expected_version, "complete", "complete", {
                "master_sha256": qa_package["master_sha256"], "qa": qa_package,
                "publications": publications,
            }, completion=True)
