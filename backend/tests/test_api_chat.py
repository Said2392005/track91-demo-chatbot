"""
Contract tests for POST /chat and GET /chat/{session_id}/history — using a FAKE agent graph via
DI override (`app.dependency_overrides[deps.get_graph]`), not the real LangGraph/LLM/Chroma
stack. This tests the router/service contract (auth enforcement, session creation vs. reuse,
tenant isolation, response shaping, transcript persistence) in isolation from whether the real
graph behaves correctly — that's what tests/test_agent_graph_integration.py already covers.
"""

from bson import ObjectId

from app.api import deps
from app.core.security import create_access_token


class FakeGraph:
    """Records every call it receives and returns a fixed, controllable state update — the
    "fake agent" the router-contract tests are built against."""

    def __init__(self, response: dict):
        self._response = response
        self.calls: list[dict] = []

    async def ainvoke(self, input_state: dict, config: dict | None = None) -> dict:
        self.calls.append({"input": input_state, "config": config})
        return {**input_state, **self._response}


def _auth_header(company_id: ObjectId, user_id: ObjectId | None = None) -> dict:
    token, _ = create_access_token(str(user_id or ObjectId()), str(company_id), "fleet_manager")
    return {"Authorization": f"Bearer {token}"}


def _override_graph(app, fake_graph: FakeGraph):
    app.dependency_overrides[deps.get_graph] = lambda: fake_graph


async def test_chat_without_auth_is_401(api_client):
    response = await api_client.post("/chat", json={"message": "hi"})
    assert response.status_code == 401


async def test_chat_creates_a_new_session_and_persists_transcript(api_client, db):
    from app.main import app

    fake_graph = FakeGraph({"response_text": "Hello! How can I help?", "final_intent": "GREETING", "citations": []})
    _override_graph(app, fake_graph)
    company_id = ObjectId()

    try:
        response = await api_client.post("/chat", json={"message": "Hi there"}, headers=_auth_header(company_id))
    finally:
        app.dependency_overrides.pop(deps.get_graph, None)

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Hello! How can I help?"
    assert body["intent"] == "GREETING"
    assert body["session_id"]
    assert len(fake_graph.calls) == 1
    assert fake_graph.calls[0]["config"]["configurable"]["thread_id"] == body["session_id"]

    session = await db.chat_sessions.find_one({"_id": ObjectId(body["session_id"])})
    assert session is not None
    assert session["company_id"] == company_id

    messages = await db.chat_messages.find({"session_id": ObjectId(body["session_id"])}).sort("created_at", 1).to_list(10)
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "Hi there"
    assert messages[1]["content"] == "Hello! How can I help?"


async def test_chat_reuses_an_existing_session(api_client, db):
    from app.main import app

    fake_graph = FakeGraph({"response_text": "ok", "final_intent": "CHITCHAT", "citations": []})
    _override_graph(app, fake_graph)
    company_id = ObjectId()
    headers = _auth_header(company_id)

    try:
        first = await api_client.post("/chat", json={"message": "turn one"}, headers=headers)
        session_id = first.json()["session_id"]

        second = await api_client.post("/chat", json={"message": "turn two", "session_id": session_id}, headers=headers)
    finally:
        app.dependency_overrides.pop(deps.get_graph, None)

    assert second.status_code == 200
    assert second.json()["session_id"] == session_id
    assert len(fake_graph.calls) == 2

    messages = await db.chat_messages.find({"session_id": ObjectId(session_id)}).sort("created_at", 1).to_list(10)
    assert len(messages) == 4  # 2 user + 2 assistant turns


async def test_chat_rejects_a_session_from_another_company(api_client, db):
    from app.main import app

    fake_graph = FakeGraph({"response_text": "ok", "final_intent": "CHITCHAT", "citations": []})
    _override_graph(app, fake_graph)
    owner_company = ObjectId()
    attacker_company = ObjectId()

    try:
        created = await api_client.post("/chat", json={"message": "hi"}, headers=_auth_header(owner_company))
        session_id = created.json()["session_id"]

        response = await api_client.post(
            "/chat", json={"message": "sneaky", "session_id": session_id}, headers=_auth_header(attacker_company)
        )
    finally:
        app.dependency_overrides.pop(deps.get_graph, None)

    assert response.status_code == 404


async def test_chat_with_malformed_session_id_is_400(api_client):
    response = await api_client.post("/chat", json={"message": "hi", "session_id": "not-an-object-id"}, headers=_auth_header(ObjectId()))
    assert response.status_code == 400


async def test_get_history_returns_persisted_messages(api_client, db):
    from app.main import app

    fake_graph = FakeGraph({"response_text": "The weather is nice.", "final_intent": "CHITCHAT", "citations": []})
    _override_graph(app, fake_graph)
    company_id = ObjectId()
    headers = _auth_header(company_id)

    try:
        created = await api_client.post("/chat", json={"message": "how are you?"}, headers=headers)
        session_id = created.json()["session_id"]

        response = await api_client.get(f"/chat/{session_id}/history", headers=headers)
    finally:
        app.dependency_overrides.pop(deps.get_graph, None)

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["content"] == "how are you?"


async def test_get_history_for_unknown_session_is_404(api_client):
    response = await api_client.get(f"/chat/{ObjectId()}/history", headers=_auth_header(ObjectId()))
    assert response.status_code == 404


async def test_get_history_with_malformed_session_id_is_400(api_client):
    response = await api_client.get("/chat/not-an-object-id/history", headers=_auth_header(ObjectId()))
    assert response.status_code == 400
