import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import SecretStr

from app.agents.client import CrewAgents
from app.schemas import DebugReport, Implementation, Plan, Review
from tests.conftest import make_candidate, make_plan, make_review


@pytest.fixture
def provider():
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(payload)
            system = " ".join(str(m.get("content", "")) for m in payload["messages"] if m["role"] == "system")
            if "Planner / Requirements Analyst" in system:
                output = make_plan()
                output.goal += " ✓"
            elif "Developer / Coder" in system:
                output = make_candidate()
            elif "Testing and Debugging" in system:
                output = DebugReport(analysis="Checks inspected", fix_guidance=[], limitations=["Mock provider reasoning"])
            elif "Code Reviewer / QA" in system:
                output = make_review()
            else:
                # Structured-output conversion may make a second request using the raw output.
                text = " ".join(str(m.get("content", "")) for m in payload["messages"])
                output = make_plan() if "files_expected" in text else make_review()
            content = output.model_dump_json()
            if "response_format" not in payload:
                content = "Thought: I have sufficient information.\nFinal Answer: " + content
            response = json.dumps({"id": "local-test", "object": "chat.completion", "created": 1,
                                   "model": payload.get("model", "gpt-4.1"), "choices": [{"index": 0,
                                   "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1", calls
    server.shutdown()
    server.server_close()
    thread.join()


async def test_real_crewai_workers_with_mock_provider(settings, provider):
    base_url, calls = provider
    settings.api_key = SecretStr("local-test-key")
    settings.base_url = base_url
    settings.agent_timeout = 60
    agents = CrewAgents(settings)
    for role, schema in (("planner", Plan), ("developer", Implementation), ("debugger", DebugReport), ("reviewer", Review)):
        result = await agents.invoke(role, {"request": "Build a calculator", "plan": make_plan().model_dump()}, schema, lambda: None)
        assert isinstance(result, schema)
        if role == "planner":
            assert result.goal.endswith("✓")
    assert len(calls) >= 4


@pytest.mark.live
async def test_optional_live_planner():
    if os.getenv("TEAM_TEST_LIVE") != "1":
        pytest.skip("Paid model integration requires TEAM_TEST_LIVE=1 and configured TEAM_API_KEY")
    from app.config import Settings
    settings = Settings()
    assert settings.api_key.get_secret_value(), "Configure TEAM_API_KEY"
    plan = await CrewAgents(settings).invoke("planner", {"request": "Create a calculator with pytest tests"}, Plan, lambda: None)
    assert plan.acceptance_criteria
