"""Static graph and secret checks; runtime acceptance still requires n8n."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "workflows"


def expressions(value):
    if isinstance(value, str):
        if value.startswith("={{"):
            yield value
    elif isinstance(value, list):
        for item in value:
            yield from expressions(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from expressions(item)


def validate() -> dict:
    manifest = json.loads((DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["n8n_version"] == "2.40.7"
    entries = {entry["id"]: entry for entry in manifest["workflows"]}
    assert len(entries) == len(manifest["workflows"])
    assert len(manifest["import_order"]) == len(entries)
    node_count = 0
    webhook_ids = set()
    webhook_paths = set()
    for workflow_id, entry in entries.items():
        workflow = json.loads((DIRECTORY / entry["file"]).read_text(encoding="utf-8"))
        assert workflow["id"] == workflow_id
        assert workflow["active"] is False
        assert all(dependency in entries for dependency in entry["depends_on"])
        nodes = {node["name"]: node for node in workflow["nodes"]}
        assert len(nodes) == len(workflow["nodes"])
        assert len({node["id"] for node in workflow["nodes"]}) == len(nodes)
        for node in workflow["nodes"]:
            node_count += 1
            assert len(node["position"]) == 2
            assert not node.get("pinData")
            for expression in expressions(node["parameters"]):
                assert expression.endswith("}}"), f"Unclosed expression in {workflow_id}/{node['name']}"
                assert "}}" not in expression[3:-2], f"Premature expression delimiter in {workflow_id}/{node['name']}"
            credential = node.get("credentials", {})
            for spec in credential.values():
                assert spec["id"] == "CL08InternalAuth" or spec["id"].startswith("__")
            if node["type"] == "n8n-nodes-base.executeWorkflow":
                assert node["parameters"]["workflowId"]["value"] in entries
            if node["type"] == "n8n-nodes-base.webhook":
                assert node.get("webhookId"), f"Missing webhookId in {workflow_id}"
                assert node["webhookId"] not in webhook_ids
                assert node["parameters"]["path"] not in webhook_paths
                webhook_ids.add(node["webhookId"])
                webhook_paths.add(node["parameters"]["path"])
            if node["type"] == "n8n-nodes-base.httpRequest":
                params = node["parameters"]
                assert params["url"].startswith(("http://api:8000/", "http://ai:8001/", "http://n8n:5678/", "https://www.googleapis.com/", "https://api.trello.com/", "={{"))
        for source, grouped in workflow["connections"].items():
            assert source in nodes
            for outputs in grouped.values():
                for branch in outputs:
                    for connection in branch:
                        assert connection["node"] in nodes
        if workflow_id != "CL08ErrorRoute01":
            assert workflow["settings"]["errorWorkflow"] == "CL08ErrorRoute01"
        raw = json.dumps(workflow)
        assert "OPENAI_API_KEY=" not in raw and "DEMO_ADMIN_PASSWORD=" not in raw

    sweep = json.loads((DIRECTORY / "dispatch_sweeper.json").read_text(encoding="utf-8"))
    assert sweep["id"] == "CL08DispatchSweep"
    nodes = {node["name"]: node for node in sweep["nodes"]}
    schedule = nodes["Five-minute dispatch schedule"]
    assert schedule["type"] == "n8n-nodes-base.scheduleTrigger"
    assert schedule["parameters"]["rule"]["interval"] == [{"field": "minutes", "minutesInterval": 5}]
    assert nodes["Load pending dispatches"]["parameters"]["url"] == "http://api:8000/api/workflow-dispatches/pending"
    assert "rows.slice(0, 20)" in nodes["Cap and expand pending batch"]["parameters"]["jsCode"]
    targets = lambda source, branch=0: [edge["node"] for edge in sweep["connections"].get(source, {}).get("main", [[]])[branch]]
    attempt = nodes["Record dispatch attempt"]
    assert attempt["parameters"]["method"] == "POST"
    assert "/api/workflow-dispatches/" in attempt["parameters"]["url"] and "/attempt" in attempt["parameters"]["url"]
    assert targets("For each pending dispatch", 1) == ["Record dispatch attempt"]
    assert targets("Record dispatch attempt") == ["Dispatch attempt authorized"]
    assert targets("Dispatch attempt authorized", 0) == ["Dispatch is approval"]
    assert targets("Dispatch attempt authorized", 1) == ["For each pending dispatch"]
    for name, path in (
        ("Trigger approved provisioning", "provision"),
        ("Trigger stored submission", "submission"),
        ("Trigger safe recovery", "recover"),
    ):
        node = nodes[name]
        params = node["parameters"]
        assert params["method"] == "POST"
        assert params["url"] == f"http://n8n:5678/webhook/clientlaunch/{path}"
        assert node["credentials"] == {"httpHeaderAuth": {"id": "CL08InternalAuth", "name": "ClientLaunch internal API"}}
        assert any(header["name"] == "Idempotency-Key" for header in params["headerParameters"]["parameters"])
        assert params["options"]["response"]["response"] == {"fullResponse": True, "neverError": True}
        assert node["onError"] == "continueRegularOutput"
        assert targets(name) == ["Webhook accepted dispatch"]
    assert nodes["Webhook accepted dispatch"]["parameters"]["conditions"]["conditions"][0]["leftValue"] == (
        "={{ Number($json.statusCode) >= 200 && Number($json.statusCode) < 300 }}")
    assert targets("Webhook accepted dispatch", 0) == ["Acknowledge accepted dispatch"]
    assert targets("Webhook accepted dispatch", 1) == ["For each pending dispatch"]
    assert targets("Dispatch is recovery", 1) == ["For each pending dispatch"]
    ack_incoming = [
        (source, index)
        for source, grouped in sweep["connections"].items()
        for index, branch in enumerate(grouped.get("main", []))
        if any(edge["node"] == "Acknowledge accepted dispatch" for edge in branch)
    ]
    assert ack_incoming == [("Webhook accepted dispatch", 0)]
    ack = nodes["Acknowledge accepted dispatch"]
    assert ack["parameters"]["method"] == "POST"
    assert "/api/workflow-dispatches/" in ack["parameters"]["url"] and "/ack" in ack["parameters"]["url"]
    assert targets("Acknowledge accepted dispatch") == ["For each pending dispatch"]

    provision = json.loads((DIRECTORY / "provision.json").read_text(encoding="utf-8"))
    folder_nodes = {node["name"]: node for node in provision["nodes"]}
    next_folder = folder_nodes["Load next child folder"]
    assert "/provisioning/folders/next" in next_folder["parameters"]["url"]
    child_claim = folder_nodes["Claim child folder operation"]["parameters"]
    assert "create_child_folder" in child_claim["jsonBody"] and "folder_id" in child_claim["jsonBody"]
    drive = json.loads((DIRECTORY / "drive.json").read_text(encoding="utf-8"))
    drive_nodes = {node["name"]: node for node in drive["nodes"]}
    assert "parent_id" in drive_nodes["Create demo folder"]["parameters"]["jsonBody"]
    assert "parents" in drive_nodes["Create Google Drive folder"]["parameters"]["jsonBody"]
    folder_edges = lambda source, branch=0: [edge["node"] for edge in provision["connections"].get(source, {}).get("main", [[]])[branch]]
    assert folder_edges("Record folder resource") == ["Load next child folder"]
    assert folder_edges("Folder needs creation", 1) == ["Load next child folder"]
    assert folder_edges("Child folder pending", 0) == ["Claim child folder operation"]
    assert folder_edges("Child folder pending", 1) == ["All child folders ready"]
    assert folder_edges("All child folders ready", 0) == ["Claim board operation"]
    assert folder_edges("Record child folder resource") == ["Load next child folder"]
    assert folder_edges("Prior child folder confirmed", 0) == ["Load next child folder"]

    recovery = json.loads((DIRECTORY / "recovery.json").read_text(encoding="utf-8"))
    recovery_nodes = {node["name"]: node for node in recovery["nodes"]}
    resume = recovery_nodes["Safe to resume remaining steps"]
    assert resume["parameters"]["conditions"]["conditions"][0]["leftValue"] == "={{ $json.resume_needed === true }}"
    assert recovery["connections"]["Safe to resume remaining steps"]["main"][0][0]["node"] == "Resume provisioning"

    reminder = json.loads((DIRECTORY / "reminder.json").read_text(encoding="utf-8"))
    reminder_nodes = {node["name"]: node for node in reminder["nodes"]}
    controlled_run = reminder_nodes["Receive controlled reminder run"]
    assert controlled_run["type"] == "n8n-nodes-base.webhook"
    assert controlled_run["parameters"]["path"] == "clientlaunch/reminder-run"
    assert controlled_run["parameters"]["authentication"] == "headerAuth"
    assert reminder["connections"]["Receive controlled reminder run"]["main"][0][0]["node"] == "Evaluate due items"
    return {"workflows": len(entries), "nodes": node_count}


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
