"""
Load test — Phase 12 requirement. Run with:

    locust -f loadtest/locustfile.py --headless -u 10 -r 2 -t 60s --host http://127.0.0.1:8000

Targets a real running instance of the FastAPI app (`uvicorn app.main:app`) — seed data must
already exist (`python -m app.db.seed_data`) since login uses the demo credentials it creates.

Without a configured LLM provider (this environment), every message that needs real generation
returns the degraded LLM_UNAVAILABLE_RESPONSE quickly rather than waiting on a real model call —
so numbers from a run here measure this stack's own overhead (routing, Mongo, Chroma retrieval,
auth, logging), not real DeepSeek call latency. Re-run once a key is configured for numbers that
include real generation latency; see docs/phase-12-testing/testing.md.
"""

import random

from locust import HttpUser, between, task

DEMO_EMAIL = "admin@cosmica-test.example"
DEMO_PASSWORD = "demo1234"

MESSAGES = [
    "Hi there",  # GREETING — template, no LLM
    "What can you do?",  # CHITCHAT — template, no LLM
    "Where is MH12AB1234?",  # LIVE_API — mock GPS + (degraded) synthesis
    "Show me MH12AB1234's trips yesterday",  # MONGO_REPO
    "How does geofencing work?",  # RAG
    "How much does the Pro plan cost per month?",  # PRICING (gated RAG)
    "What does AIS-140 mean?",  # GENERAL_KNOWLEDGE
]


class FleetChatUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        response = self.client.post("/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        self.token = response.json().get("access_token", "")
        self.session_id = None

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    @task(6)
    def send_chat_message(self):
        body = {"message": random.choice(MESSAGES)}
        if self.session_id:
            body["session_id"] = self.session_id
        response = self.client.post("/chat", json=body, headers=self._headers)
        if response.status_code == 200:
            self.session_id = response.json().get("session_id", self.session_id)

    @task(1)
    def get_history(self):
        if self.session_id:
            self.client.get(f"/chat/{self.session_id}/history", headers=self._headers, name="/chat/[session_id]/history")

    @task(1)
    def health_check(self):
        self.client.get("/health")
