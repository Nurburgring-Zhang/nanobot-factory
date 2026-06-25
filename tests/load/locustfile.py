"""Locust load-test harness for the 12-service + 1-gateway architecture.

P6-Fix-B-6-2: 1000-concurrent load test through the api-gateway.

Architecture under test:
    api-gateway (:8000) routes to 12 microservices:
        user-service       :8001  (auth/users/roles)
        asset-service      :8002  (assets/items/DAM/OSS/library)
        annotation-service :8003  (annotations/tasks)
        cleaning-service   :8004  (clean operators)
        scoring-service    :8005  (score operators)
        dataset-service    :8006  (datasets)
        evaluation-service :8007  (evaluations)
        agent-service      :8008  (agents/agent_tasks)
        workflow-service   :8009  (workflows)
        notification-service :8010 (notifications)
        search-service     :8011  (search)
        collection-service :8012  (collections)

Five user personas distribute across all 12 services:
    AnonymousUser     - gateway-level /healthz, /readyz  (40%)
    ViewerUser        - user + notification + workflow   (15%)
    AnnotatorUser     - annotation + asset                (20%)
    ReviewerUser      - eval + clean + score + search     (15%)
    AdminUser         - agent + dataset + collection + asset (10%)

Failure policy (inherited from P2-3-W1):
    - 5xx and connection errors ARE counted as failures (system fault).
    - 4xx (auth missing, not-found, validation) are NOT failures
      (they are expected business outcomes during load tests).
    - 429 (rate limit) is NOT a failure (token-bucket working as designed).

Setup:
    Before the swarm spawns, ``setup_users`` creates a pool of test users in
    the IMDF users table (SQLite at backend/imdf/data/imdf.db) so login
    traffic has real credentials.

Runtime:
    Headless 5-min run:
        locust -f tests/load/locustfile.py --headless -u 1000 -r 50 \
            --run-time 5m --host http://127.0.0.1:8000 \
            --html reports/locust_1000_report.html \
            --csv reports/locust_1000_stats
"""
from __future__ import annotations

import logging
import os
import random
import time
from pathlib import Path
from typing import Optional

from locust import FastHttpUser, between, events, task

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HOST = os.environ.get("LOCUST_HOST", "http://127.0.0.1:8000")
USERS_PER_ROLE = int(os.environ.get("LOCUST_USERS_PER_ROLE", "100"))  # 4 roles x 100 = 400 users
PASSWORD = os.environ.get("LOCUST_TEST_PASSWORD", "LoadTest123!Pass")
USERNAME_PREFIX = "locust_load_"

LOG = logging.getLogger("locustfile")

# Service to gateway path prefix mapping (for per-service analysis)
SERVICE_PREFIXES = {
    "user-service":         ["/api/v1/users", "/api/v1/roles", "/api/v1/auth", "/auth"],
    "asset-service":        ["/api/v1/assets", "/api/v1/items"],
    "annotation-service":   ["/api/v1/annotations", "/api/v1/tasks"],
    "cleaning-service":     ["/api/v1/clean"],
    "scoring-service":      ["/api/v1/score"],
    "dataset-service":      ["/api/v1/datasets"],
    "evaluation-service":   ["/api/v1/evaluations"],
    "agent-service":        ["/api/v1/agents", "/api/v1/agent_tasks"],
    "workflow-service":     ["/api/v1/workflows"],
    "notification-service": ["/api/v1/notifications"],
    "search-service":       ["/api/v1/search"],
    "collection-service":   ["/api/v1/collections"],
}


# ---------------------------------------------------------------------------
# Seed users via direct DB write
# ---------------------------------------------------------------------------
def _seed_users() -> int:
    """Insert USERS_PER_ROLE per role into the IMDF users table."""
    import sqlite3

    backend_imdf = Path(__file__).resolve().parents[2] / "backend" / "imdf"
    db_path = backend_imdf / "data" / "imdf.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    pwd_hash = _hash_password(PASSWORD)

    roles = ["viewer", "annotator", "reviewer", "admin"]
    inserted = 0
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'viewer',
                enabled INTEGER DEFAULT 1,
                max_datasets INTEGER DEFAULT 10,
                max_storage_mb INTEGER DEFAULT 1024,
                max_api_calls_per_day INTEGER DEFAULT 1000,
                created_at TEXT DEFAULT (datetime('now'))
            )"""
        )
        for role in roles:
            for i in range(USERS_PER_ROLE):
                username = f"{USERNAME_PREFIX}{role}_{i:04d}"
                try:
                    conn.execute(
                        "INSERT INTO users(username,password_hash,role,enabled,created_at) "
                        "VALUES(?,?,?,1,datetime('now'))",
                        (username, pwd_hash, role),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    pass
        conn.commit()
    LOG.info("Seeded %d test users (4 roles x %d) into %s", inserted, USERS_PER_ROLE, db_path)
    return inserted


def _hash_password(plain: str) -> str:
    """Mirror AuthService._hash_password: try argon2 -> passlib/bcrypt -> sha256."""
    try:
        from argon2 import PasswordHasher
        return PasswordHasher().hash(plain)
    except Exception:
        pass
    try:
        from passlib.context import CryptContext
        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        raw = plain.encode("utf-8")[:72]
        try:
            return ctx.hash(raw.decode("utf-8"))
        except ValueError:
            pass
    except Exception:
        pass
    import hashlib
    import secrets
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + plain).encode()).hexdigest()
    return f"sha256${salt}${h}"


# ---------------------------------------------------------------------------
# Failure policy
# ---------------------------------------------------------------------------
def _is_failure(response) -> bool:
    """5xx + connection errors = failure. 4xx + 429 = expected business outcome."""
    if response is None:
        return True
    if not getattr(response, "ok", True):
        return True
    return response.status_code >= 500


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------
class _BaseUser(FastHttpUser):
    abstract = True
    wait_time = between(0.1, 0.8)  # tight enough to actually generate 1000 RPS

    def on_start(self):
        self.token: Optional[str] = None
        self.username: Optional[str] = None
        self.role: str = "viewer"

    # Response helpers (override default failure policy)
    def _get(self, path: str, name: Optional[str] = None, **kw):
        catch_response = kw.pop("catch_response", True)
        with self.client.get(
            path, name=name or path, catch_response=catch_response, **kw
        ) as resp:
            if catch_response:
                if _is_failure(resp):
                    resp.failure(f"{resp.status_code} {path}")
                else:
                    resp.success()

    def _post(self, path: str, json=None, name: Optional[str] = None, **kw):
        catch_response = kw.pop("catch_response", True)
        with self.client.post(
            path, json=json, name=name or path, catch_response=catch_response, **kw
        ) as resp:
            if catch_response:
                if _is_failure(resp):
                    resp.failure(f"{resp.status_code} {path}")
                else:
                    resp.success()

    def _login(self, role: str) -> bool:
        """Login as a random user of the given role. Returns True on success."""
        username = f"{USERNAME_PREFIX}{role}_{random.randint(0, USERS_PER_ROLE - 1):04d}"
        with self.client.post(
            "/auth/login",
            json={"username": username, "password": PASSWORD},
            name="/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"{role} login {resp.status_code}")
                return False
            try:
                body = resp.json()
                self.token = body.get("data", {}).get("access_token")
                if self.token:
                    self.username = username
                    self.role = role
                    self.client.headers["Authorization"] = f"Bearer {self.token}"
                    resp.success()
                    return True
                resp.failure("login: no access_token in body")
                return False
            except Exception as e:
                resp.failure(f"login parse: {e}")
                return False


# ---------------------------------------------------------------------------
# Persona 1: Anonymous (40%) — public gateway probes
# ---------------------------------------------------------------------------
class AnonymousUser(_BaseUser):
    weight = 4

    @task(5)
    def healthz(self):
        self._get("/healthz")

    @task(3)
    def readyz(self):
        self._get("/readyz")

    @task(2)
    def api_v1_health(self):
        self._get("/api/v1/health")

    @task(1)
    def api_v1_health_ready(self):
        self._get("/api/v1/health/ready")


# ---------------------------------------------------------------------------
# Persona 2: Viewer (15%) — user + notification + workflow
# ---------------------------------------------------------------------------
class ViewerUser(_BaseUser):
    weight = 2

    def on_start(self):
        super().on_start()
        self._login("viewer")

    @task(5)
    def users_me(self):
        self._get("/api/v1/users/me")

    @task(3)
    def roles(self):
        self._get("/api/v1/roles")

    @task(3)
    def notifications(self):
        self._get("/api/v1/notifications")

    @task(2)
    def workflows(self):
        self._get("/api/v1/workflows")

    @task(2)
    def workflow_templates(self):
        self._get("/api/v1/workflows/templates")


# ---------------------------------------------------------------------------
# Persona 3: Annotator (20%) — annotation + asset
# ---------------------------------------------------------------------------
class AnnotatorUser(_BaseUser):
    weight = 3

    def on_start(self):
        super().on_start()
        self._login("annotator")

    @task(6)
    def list_assets(self):
        self._get("/api/v1/assets")

    @task(4)
    def list_tasks(self):
        self._get("/api/v1/tasks")

    @task(3)
    def list_annotations(self):
        self._get("/api/v1/annotations")

    @task(2)
    def asset_models(self):
        self._get("/api/v1/assets/models")

    @task(2)
    def list_items(self):
        self._get("/api/v1/items")


# ---------------------------------------------------------------------------
# Persona 4: Reviewer (15%) — eval + clean + score + search
# ---------------------------------------------------------------------------
class ReviewerUser(_BaseUser):
    weight = 2

    def on_start(self):
        super().on_start()
        self._login("reviewer")

    @task(4)
    def evaluations(self):
        self._get("/api/v1/evaluations")

    @task(3)
    def clean_operators(self):
        self._get("/api/v1/clean/operators")

    @task(3)
    def score_operators(self):
        self._get("/api/v1/score/operators")

    @task(3)
    def search(self):
        self._get("/api/v1/search")

    @task(2)
    def workflow_runs(self):
        self._get("/api/v1/workflows")


# ---------------------------------------------------------------------------
# Persona 5: Admin (10%) — agent + dataset + collection + heavy read
# ---------------------------------------------------------------------------
class AdminUser(_BaseUser):
    weight = 2

    def on_start(self):
        super().on_start()
        self._login("admin")

    @task(3)
    def agents(self):
        self._get("/api/v1/agents")

    @task(2)
    def agent_tasks(self):
        self._get("/api/v1/agent_tasks")

    @task(2)
    def agent_types(self):
        self._get("/api/v1/agents/types")

    @task(2)
    def datasets(self):
        self._get("/api/v1/datasets")

    @task(2)
    def collections(self):
        self._get("/api/v1/collections")

    @task(2)
    def list_projects(self):
        self._get("/api/v1/workflows")

    @task(1)
    def create_project(self):
        self._post(
            "/api/v1/workflows",
            json={
                "name": f"load-test-{random.randint(1, 99999)}",
                "description": "auto from locust",
            },
            name="/api/v1/workflows [POST]",
        )


# ---------------------------------------------------------------------------
# Test-start hook
# ---------------------------------------------------------------------------
@events.test_start.add_listener
def _on_test_start(environment, **kwargs):
    LOG.info("Locust starting: seeding test users...")
    t0 = time.time()
    try:
        n = _seed_users()
        LOG.info("Seeded %d users in %.2fs", n, time.time() - t0)
    except Exception as e:
        LOG.exception("Failed to seed users: %s", e)


# ---------------------------------------------------------------------------
# Test-stop hook: write summary to JSON for report consumption
# ---------------------------------------------------------------------------
@events.test_stop.add_listener
def _on_test_stop(environment, **kwargs):
    """Write final stats to JSON so the report builder can parse it."""
    try:
        import json
        stats = environment.stats
        rows = []
        for key, entry in stats.entries.items():
            # entry.name is locust's tagged name; entry.method is GET/POST etc.
            try:
                num = entry.num_requests
                fails = entry.num_failures
                median = entry.get_response_time_percentile(0.5)
                p95 = entry.get_response_time_percentile(0.95)
                p99 = entry.get_response_time_percentile(0.99)
                avg = entry.avg_response_time
                rps = entry.total_rps if hasattr(entry, "total_rps") else 0
                max_rt = entry.max_response_time
                rows.append({
                    "name": entry.name,
                    "method": entry.method,
                    "num_requests": num,
                    "num_failures": fails,
                    "median_ms": median,
                    "p95_ms": p95,
                    "p99_ms": p99,
                    "avg_ms": avg,
                    "max_ms": max_rt,
                    "rps": rps,
                })
            except Exception as e:
                LOG.warning("skipping entry %s: %s", key, e)
        # Write to a stable path
        out = Path(__file__).resolve().parent / "locust_final_stats.json"
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        LOG.info("Wrote %d stat rows to %s", len(rows), out)
    except Exception as e:
        LOG.exception("test_stop hook failed: %s", e)
