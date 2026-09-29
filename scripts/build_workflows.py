"""Build deterministic, secret-free n8n 2.40.7 workflow exports."""

import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "workflows"
IDS = {
    "drive": "CL08DriveFolder01",
    "trello": "CL08TrelloBoard1",
    "error": "CL08ErrorRoute01",
    "task_sync": "CL08TaskSync001",
    "intake": "CL08DealIntake01",
    "provision": "CL08Provision001",
    "submission": "CL08Submission01",
    "reminder": "CL08Reminder001",
    "recovery": "CL08Recovery0001",
    "dispatch_sweeper": "CL08DispatchSweep",
}
INTERNAL_CREDENTIAL = {"httpHeaderAuth": {"id": "CL08InternalAuth", "name": "ClientLaunch internal API"}}
DRIVE_CREDENTIAL = {"googleDriveOAuth2Api": {"id": "__GOOGLE_DRIVE_CREDENTIAL_ID__", "name": "Google Drive OAuth2 (configure)"}}
TRELLO_CREDENTIAL = {"trelloApi": {"id": "__TRELLO_CREDENTIAL_ID__", "name": "Trello API (configure)"}}
SMTP_CREDENTIAL = {"smtp": {"id": "__SMTP_CREDENTIAL_ID__", "name": "Authorized SMTP (configure)"}}
NOTES = {
    "drive": "Claimed folder operation → DEMO simulator or connected Drive → provider result. Reconcile uncertain writes before retry.",
    "trello": "Claimed board operation → DEMO simulator or connected Trello → board and To Do list IDs.",
    "error": "Automatic execution failures are persisted in the business exception queue.",
    "intake": "Signed event → API verification and durable receipt → prompt acknowledgment → AI draft. Duplicates stop after acknowledgment.",
    "provision": "Approved plan → claimed folder/board writes → persisted resources → task sync → approved welcome.",
    "task_sync": "Pending checklist cards → claim each write → DEMO or connected Trello → persist provider card ID and status.",
    "submission": "Stored client submission → idempotent checklist processing → changed task cards.",
    "reminder": "Daily schedule or authenticated DEMO run → due query → approved pending reminders → DEMO outbox or authorized SMTP → dispatch acknowledgment.",
    "recovery": "Ledger reconciliation → resume remaining steps after confirmed outcomes or retry known failed steps. Unknown outcomes stay paused for review.",
    "dispatch_sweeper": "Every five minutes, replay at most 20 pending approval, submission, or recovery triggers. Record each attempt so failed rows move behind untouched work. Acknowledge only a webhook 2xx.",
}


class Workflow:
    def __init__(self, key: str, name: str, *, error: bool = True):
        self.key = key
        self.name = name
        self.nodes: list[dict] = []
        self.connections: dict = {}
        self.settings = {"executionOrder": "v1", "saveDataErrorExecution": "all", "saveDataSuccessExecution": "all", "executionTimeout": 300}
        if error:
            self.settings["errorWorkflow"] = IDS["error"]
        self.node("Workflow contract", "stickyNote", 1, 120, 20,
                  {"content": f"## {name}\n{NOTES[key]}\n\nInput/output contracts: manifest.json.",
                   "height": 170, "width": 450})

    def node(self, name: str, kind: str, version: int | float, x: int, y: int, parameters: dict, *, credentials: dict | None = None, settings: dict | None = None):
        node = {"parameters": parameters, "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"clientlaunch/{self.key}/{name}")),
                "name": name, "type": f"n8n-nodes-base.{kind}", "typeVersion": version, "position": [x, y]}
        if credentials:
            node["credentials"] = credentials
        if settings:
            node["settings"] = settings
        self.nodes.append(node)
        return name

    def link(self, source: str, target: str, branch: int = 0):
        branches = self.connections.setdefault(source, {}).setdefault("main", [])
        while len(branches) <= branch:
            branches.append([])
        branches[branch].append({"node": target, "type": "main", "index": 0})

    def webhook(self, name: str, path: str, x=120, y=300, *, signed: bool = False):
        params = {"httpMethod": "POST", "path": path,
                  "responseMode": "responseNode" if signed else "onReceived",
                  "options": {} if signed else {"responseCode": 202}}
        if not signed:
            params["authentication"] = "headerAuth"
        node_name = self.node(name, "webhook", 2.1, x, y, params,
                              credentials=None if signed else INTERNAL_CREDENTIAL)
        # n8n requires webhookId for the published URL to use `path` exactly.
        # Without it, imported nodes register workflowId/nodeName/path instead.
        self.nodes[-1]["webhookId"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"clientlaunch/{self.key}/{name}/webhook"))
        return node_name

    def http(self, name: str, method: str, url: str, x: int, y: int, *, body: str | None = None,
             headers: list[dict] | None = None, credentials: dict | None = INTERNAL_CREDENTIAL,
             retry_reads: bool = False):
        params = {"method": method, "url": url, "options": {"timeout": 30000}}
        if credentials:
            credential_type = next(iter(credentials))
            if credential_type == "httpHeaderAuth":
                params.update({"authentication": "genericCredentialType", "genericAuthType": credential_type})
            else:
                params.update({"authentication": "predefinedCredentialType", "nodeCredentialType": credential_type})
        if body is not None:
            params.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
        if headers:
            params.update({"sendHeaders": True, "headerParameters": {"parameters": headers}})
        node_settings = {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000} if retry_reads else None
        return self.node(name, "httpRequest", 4.2, x, y, params, credentials=credentials, settings=node_settings)

    def conditional(self, name: str, expression: str, x: int, y: int):
        params = {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                                 "combinator": "and", "conditions": [{"id": str(uuid.uuid5(uuid.NAMESPACE_URL, name)),
                                     "leftValue": expression, "rightValue": "", "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}}
        return self.node(name, "if", 2.2, x, y, params)

    def subworkflow(self, name: str, workflow_id: str, x: int, y: int):
        return self.node(name, "executeWorkflow", 1.2, x, y,
                         {"source": "database", "workflowId": {"__rl": True, "value": workflow_id, "mode": "id"},
                          "mode": "each", "options": {"waitForSubWorkflow": True}})

    def save(self) -> dict:
        data = {"id": IDS[self.key], "name": self.name, "active": False, "nodes": self.nodes,
                "connections": self.connections, "settings": self.settings, "staticData": None, "pinData": {}, "tags": []}
        (OUT / f"{self.key}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return data


def drive_workflow():
    w = Workflow("drive", "ClientLaunch | Provision Drive folder")
    w.node("Accept folder operation", "executeWorkflowTrigger", 1.1, 120, 300, {"inputSource": "passthrough"})
    w.conditional("Use connected Drive", "={{ $json.connector_mode === 'connected' }}", 360, 300)
    w.http("Create demo folder", "POST", "http://api:8000/sim/drive/folders", 620, 420,
           body="={{ JSON.stringify({onboarding_id:$json.onboarding_id,name:$json.request_payload.name,parent_id:$json.request_payload.parent_id,idempotency_key:$json.idempotency_key}) }}")
    w.http("Create Google Drive folder", "POST", "https://www.googleapis.com/drive/v3/files?fields=id,name,webViewLink", 620, 180,
           body="={{ JSON.stringify({name:$json.request_payload.name,mimeType:'application/vnd.google-apps.folder',...($json.request_payload.parent_id ? {parents:[$json.request_payload.parent_id]} : {})}) }}",
           credentials=DRIVE_CREDENTIAL)
    w.link("Accept folder operation", "Use connected Drive")
    w.link("Use connected Drive", "Create Google Drive folder", 0)
    w.link("Use connected Drive", "Create demo folder", 1)
    w.save()


def trello_workflow():
    w = Workflow("trello", "ClientLaunch | Provision Trello board")
    w.node("Accept board operation", "executeWorkflowTrigger", 1.1, 120, 300, {"inputSource": "passthrough"})
    w.conditional("Use connected Trello", "={{ $json.connector_mode === 'connected' }}", 360, 300)
    w.http("Create demo board", "POST", "http://api:8000/sim/trello/boards", 620, 420,
           body="={{ JSON.stringify({onboarding_id:$json.onboarding_id,name:$json.request_payload.name,idempotency_key:$json.idempotency_key}) }}")
    w.http("Create Trello board", "POST", "={{ 'https://api.trello.com/1/boards?name=' + encodeURIComponent($json.request_payload.name) + '&defaultLists=true' }}", 620, 180,
           credentials=TRELLO_CREDENTIAL)
    w.http("Read default Trello lists", "GET", "={{ 'https://api.trello.com/1/boards/' + $('Create Trello board').first().json.id + '/lists?fields=id,name' }}", 870, 180,
           credentials=TRELLO_CREDENTIAL, retry_reads=True)
    w.node("Select To Do list and board result", "code", 2, 1120, 180,
           {"mode": "runOnceForAllItems", "jsCode": "const board = $('Create Trello board').first().json;\nconst lists = $input.all().map(item => item.json);\nconst todo = lists.find(item => /^to do$/i.test(item.name)) ?? lists[0];\nif (!todo?.id) throw new Error('Board created but no Trello list was returned');\nreturn [{json:{id:board.id,url:board.url ?? board.shortUrl,name:board.name,todo_list_id:todo.id}}];"})
    w.link("Accept board operation", "Use connected Trello")
    w.link("Use connected Trello", "Create Trello board", 0)
    w.link("Use connected Trello", "Create demo board", 1)
    w.link("Create Trello board", "Read default Trello lists")
    w.link("Read default Trello lists", "Select To Do list and board result")
    w.save()


def error_workflow():
    w = Workflow("error", "ClientLaunch | Shared execution error", error=False)
    w.node("Catch triggered failure", "errorTrigger", 1, 120, 300, {})
    w.http("Queue business exception", "POST", "http://api:8000/api/workflow-errors", 420, 300,
           body="={{ JSON.stringify({workflow_id:$json.workflow?.id,execution_id:$json.execution?.id,node:$json.execution?.lastNodeExecuted,message:$json.execution?.error?.message}) }}")
    w.link("Catch triggered failure", "Queue business exception")
    w.save()


def intake_workflow():
    w = Workflow("intake", "ClientLaunch | Receive won deal")
    w.webhook("Receive signed won deal", "clientlaunch/won-deal", signed=True)
    w.http("Verify and persist deal", "POST", "http://api:8000/api/events/won-deal", 390, 300,
           body="={{ JSON.stringify($json.body) }}",
           headers=[{"name": "X-ClientLaunch-Signature", "value": "={{ $json.headers['x-clientlaunch-signature'] }}"}])
    w.nodes[-1]["parameters"]["options"]["response"] = {"response": {"fullResponse": True, "neverError": True}}
    w.node("Acknowledge verified deal", "respondToWebhook", 1.4, 650, 300,
           {"respondWith": "json", "responseBody": "={{ JSON.stringify($json.statusCode >= 400 ? {accepted:false,error:$json.body?.detail || $json.body?.message || 'Rejected'} : {accepted:true,onboarding_id:$json.body.onboarding_id,duplicate:$json.body.duplicate}) }}",
            "options": {"responseCode": "={{ $json.statusCode }}"}})
    w.conditional("Already received", "={{ $('Verify and persist deal').first().json.statusCode >= 400 || $('Verify and persist deal').first().json.body.duplicate === true }}", 900, 300)
    w.http("Load onboarding", "GET", "={{ 'http://api:8000/api/onboardings/' + $('Verify and persist deal').first().json.body.onboarding_id }}", 1160, 400, retry_reads=True)
    w.http("Draft AI plan", "POST", "http://ai:8001/plan", 1430, 400,
           body="={{ JSON.stringify({onboarding_id:$json.onboarding.id,client_name:$json.onboarding.client_name,approved_scope:$json.deal.approved_scope,purchased_services:$json.deal.services,reference_date:$json.onboarding.reference_date}) }}")
    w.http("Store review draft", "POST", "={{ 'http://api:8000/api/onboardings/' + $('Load onboarding').first().json.onboarding.id + '/plan' }}", 1700, 400,
           body="={{ JSON.stringify($json) }}")
    w.link("Receive signed won deal", "Verify and persist deal")
    w.link("Verify and persist deal", "Acknowledge verified deal")
    w.link("Acknowledge verified deal", "Already received")
    w.link("Already received", "Load onboarding", 1)
    w.link("Load onboarding", "Draft AI plan")
    w.link("Draft AI plan", "Store review draft")
    w.save()


def provision_workflow():
    w = Workflow("provision", "ClientLaunch | Approved provisioning")
    w.webhook("Receive approved plan", "clientlaunch/provision")
    w.http("Load approved onboarding", "GET", "={{ 'http://api:8000/api/onboardings/' + $json.body.onboarding_id }}", 390, 300, retry_reads=True)
    oid = "$('Load approved onboarding').first().json.onboarding.id"
    w.http("Claim folder operation", "POST", f"={{{{ 'http://api:8000/api/onboardings/' + {oid} + '/provisioning/claim' }}}}", 680, 300,
           body="={{ JSON.stringify({system:'drive',action:'create_folder',request_payload:{name:$json.onboarding.folder_name} }) }}")
    w.conditional("Folder needs creation", "={{ $json.execute === true }}", 950, 300)
    w.subworkflow("Provision Drive folder", IDS["drive"], 1210, 180)
    w.http("Record folder resource", "POST", f"={{{{ 'http://api:8000/api/onboardings/' + {oid} + '/provisioning/' + $('Claim folder operation').first().json.operation_id + '/complete' }}}}", 1480, 180,
           body="={{ JSON.stringify({outcome:'success',external_id:$json.external_id || $json.id,url:$json.url || $json.webViewLink,name:$json.name}) }}")
    w.http("Load next child folder", "GET", f"={{{{ 'http://api:8000/api/onboardings/' + {oid} + '/provisioning/folders/next' }}}}", 1740, 300,
           retry_reads=True)
    w.conditional("Child folder pending", "={{ $json.done !== true && $json.blocked !== true && !!$json.folder?.id }}", 2010, 300)
    w.conditional("All child folders ready", "={{ $json.done === true }}", 2280, 490)
    w.http("Claim child folder operation", "POST", f"={{{{ 'http://api:8000/api/onboardings/' + {oid} + '/provisioning/claim' }}}}", 2280, 130,
           body="={{ JSON.stringify({system:'drive',action:'create_child_folder',folder_id:$json.folder.id}) }}")
    w.conditional("Child folder write authorized", "={{ $json.execute === true }}", 2550, 130)
    w.conditional("Prior child folder confirmed", "={{ $json.status === 'succeeded' }}", 2820, 320)
    w.subworkflow("Provision Drive child folder", IDS["drive"], 2820, 20)
    w.http("Record child folder resource", "POST", f"={{{{ 'http://api:8000/api/onboardings/' + {oid} + '/provisioning/' + $('Claim child folder operation').last().json.operation_id + '/complete' }}}}", 3090, 20,
           body="={{ JSON.stringify({outcome:'success',external_id:$json.external_id || $json.id,url:$json.url || $json.webViewLink,name:$json.name}) }}")
    w.http("Claim board operation", "POST", f"={{{{ 'http://api:8000/api/onboardings/' + {oid} + '/provisioning/claim' }}}}", 3360, 490,
           body="={{ JSON.stringify({system:'trello',action:'create_board',request_payload:{name:$('Load approved onboarding').first().json.onboarding.board_name} }) }}")
    w.conditional("Board needs creation", "={{ $json.execute === true }}", 3630, 490)
    w.subworkflow("Provision Trello board", IDS["trello"], 3900, 360)
    w.http("Record board resource", "POST", f"={{{{ 'http://api:8000/api/onboardings/' + {oid} + '/provisioning/' + $('Claim board operation').first().json.operation_id + '/complete' }}}}", 4170, 360,
           body="={{ JSON.stringify({outcome:'success',external_id:$json.external_id || $json.id,url:$json.url || $json.shortUrl,name:$json.name,todo_list_id:$json.todo_list_id}) }}")
    w.http("Trigger Trello task sync", "POST", "http://n8n:5678/webhook/clientlaunch/task-sync", 4440, 490,
           body="={{ JSON.stringify({onboarding_id:$('Load approved onboarding').first().json.onboarding.id}) }}")
    w.http("Queue approved welcome", "POST", f"={{{{ 'http://api:8000/api/onboardings/' + {oid} + '/welcome' }}}}", 4710, 490,
           body="={{ JSON.stringify({}) }}")
    w.conditional("Welcome requires SMTP", "={{ $json.dispatch_required === true }}", 4980, 490)
    w.node("Send authorized welcome", "emailSend", 2.1, 5250, 360,
           {"fromEmail": "={{ $json.from }}", "toEmail": "={{ $json.to }}",
            "subject": "={{ $json.subject }}", "emailFormat": "text", "text": "={{ $json.body }}", "options": {}},
           credentials=SMTP_CREDENTIAL)
    w.http("Acknowledge SMTP welcome", "POST",
           "={{ 'http://api:8000/api/outbox/' + $('Queue approved welcome').first().json.id + '/ack' }}", 5520, 360,
           body="={{ JSON.stringify({provider_message_id:$json.messageId || $json.message_id}) }}")
    w.link("Receive approved plan", "Load approved onboarding")
    w.link("Load approved onboarding", "Claim folder operation")
    w.link("Claim folder operation", "Folder needs creation")
    w.link("Folder needs creation", "Provision Drive folder", 0)
    w.link("Provision Drive folder", "Record folder resource")
    w.link("Record folder resource", "Load next child folder")
    w.link("Folder needs creation", "Load next child folder", 1)
    w.link("Load next child folder", "Child folder pending")
    w.link("Child folder pending", "Claim child folder operation", 0)
    w.link("Child folder pending", "All child folders ready", 1)
    w.link("All child folders ready", "Claim board operation", 0)
    w.link("Claim child folder operation", "Child folder write authorized")
    w.link("Child folder write authorized", "Provision Drive child folder", 0)
    w.link("Provision Drive child folder", "Record child folder resource")
    w.link("Record child folder resource", "Load next child folder")
    w.link("Child folder write authorized", "Prior child folder confirmed", 1)
    w.link("Prior child folder confirmed", "Load next child folder", 0)
    w.link("Claim board operation", "Board needs creation")
    w.link("Board needs creation", "Provision Trello board", 0)
    w.link("Provision Trello board", "Record board resource")
    w.link("Record board resource", "Trigger Trello task sync")
    w.link("Board needs creation", "Trigger Trello task sync", 1)
    w.link("Trigger Trello task sync", "Queue approved welcome")
    w.link("Queue approved welcome", "Welcome requires SMTP")
    w.link("Welcome requires SMTP", "Send authorized welcome", 0)
    w.link("Send authorized welcome", "Acknowledge SMTP welcome")
    w.save()


def submission_workflow():
    w = Workflow("submission", "ClientLaunch | Process client intake")
    w.webhook("Receive stored submission", "clientlaunch/submission")
    w.http("Apply checklist updates", "POST", "={{ 'http://api:8000/api/client-submissions/' + $json.body.submission_id + '/process' }}", 400, 300,
           body="={{ JSON.stringify({}) }}")
    w.http("Trigger changed Trello tasks", "POST", "http://n8n:5678/webhook/clientlaunch/task-sync", 680, 300,
           body="={{ JSON.stringify({onboarding_id:$json.onboarding_id}) }}")
    w.link("Receive stored submission", "Apply checklist updates")
    w.link("Apply checklist updates", "Trigger changed Trello tasks")
    w.save()


def task_sync_workflow():
    w = Workflow("task_sync", "ClientLaunch | Sync checklist to Trello")
    w.webhook("Receive task sync request", "clientlaunch/task-sync")
    oid = "$('Receive task sync request').first().json.body.onboarding_id"
    card = "$('For each pending card').item.json"
    w.http("Reconcile expired card claims", "POST", f"={{{{ 'http://api:8000/api/onboardings/' + {oid} + '/task-sync/reconcile' }}}}", 260, 300,
           body="={{ JSON.stringify({}) }}")
    w.http("Load pending card operations", "GET", f"={{{{ 'http://api:8000/api/onboardings/' + {oid} + '/task-sync/pending' }}}}", 390, 300, retry_reads=True)
    w.node("For each pending card", "splitInBatches", 3, 650, 300, {"batchSize": 1, "options": {}})
    w.http("Claim card operation", "POST", f"={{{{ 'http://api:8000/api/onboardings/' + {oid} + '/task-sync/' + {card}.operation_id + '/claim' }}}}", 900, 300,
           body=f"={{{{ JSON.stringify({{expected_status:{card}.status,expected_idempotency_key:{card}.idempotency_key}}) }}}}")
    w.conditional("Card write authorized", "={{ $json.execute === true }}", 1150, 300)
    w.conditional("Use connected Trello cards", f"={{{{ {card}.connector_mode === 'connected' }}}}", 1400, 300)
    w.conditional("Connected card is new", f"={{{{ {card}.action === 'create' }}}}", 1650, 130)
    w.conditional("Demo card is new", f"={{{{ {card}.action === 'create' }}}}", 1650, 470)
    w.http("Create Trello card", "POST", f"={{{{ 'https://api.trello.com/1/cards?idList=' + encodeURIComponent({card}.todo_list_id) + '&name=' + encodeURIComponent({card}.title) + '&desc=' + encodeURIComponent('Status: ' + {card}.status + '\\n' + {card}.description) }}}}", 1900, 40,
           credentials=TRELLO_CREDENTIAL)
    w.http("Update Trello card", "PUT", f"={{{{ 'https://api.trello.com/1/cards/' + encodeURIComponent({card}.external_card_id) + '?desc=' + encodeURIComponent('Status: ' + {card}.status + '\\n' + {card}.description) + '&dueComplete=' + ({card}.status === 'completed' ? 'true' : 'false') }}}}", 1900, 220,
           credentials=TRELLO_CREDENTIAL)
    w.http("Create demo card", "POST", "http://api:8000/sim/trello/cards", 1900, 390,
           body=f"={{{{ JSON.stringify({{board_id:{card}.external_board_id,name:{card}.title,description:{card}.description,due_date:{card}.due_date,status:{card}.status,idempotency_key:{card}.idempotency_key}}) }}}}")
    w.http("Update demo card", "PATCH", f"={{{{ 'http://api:8000/sim/trello/cards/' + {card}.external_card_id }}}}", 1900, 550,
           body=f"={{{{ JSON.stringify({{status:{card}.status,idempotency_key:{card}.idempotency_key}}) }}}}")
    w.http("Record synced card", "POST", f"={{{{ 'http://api:8000/api/onboardings/' + {oid} + '/task-sync/' + {card}.operation_id + '/complete' }}}}", 2180, 300,
           body=f"={{{{ JSON.stringify({{external_id:$json.external_id || $json.id || {card}.external_card_id,status:{card}.status}}) }}}}")
    w.link("Receive task sync request", "Reconcile expired card claims")
    w.link("Reconcile expired card claims", "Load pending card operations")
    w.link("Load pending card operations", "For each pending card")
    w.link("For each pending card", "Claim card operation", 1)
    w.link("Claim card operation", "Card write authorized")
    w.link("Card write authorized", "Use connected Trello cards", 0)
    w.link("Card write authorized", "For each pending card", 1)
    w.link("Use connected Trello cards", "Connected card is new", 0)
    w.link("Use connected Trello cards", "Demo card is new", 1)
    w.link("Connected card is new", "Create Trello card", 0)
    w.link("Connected card is new", "Update Trello card", 1)
    w.link("Demo card is new", "Create demo card", 0)
    w.link("Demo card is new", "Update demo card", 1)
    for connector_node in ("Create Trello card", "Update Trello card", "Create demo card", "Update demo card"):
        w.link(connector_node, "Record synced card")
    w.link("Record synced card", "For each pending card")
    w.save()


def reminder_workflow():
    w = Workflow("reminder", "ClientLaunch | Evaluate reminders")
    w.node("Daily reminder schedule", "scheduleTrigger", 1.2, 120, 300,
           {"rule": {"interval": [{"field": "hours", "hoursInterval": 24}]}})
    w.webhook("Receive controlled reminder run", "clientlaunch/reminder-run", 120, 520)
    w.http("Evaluate due items", "POST", "http://api:8000/api/reminders/evaluate", 420, 300,
           body="={{ JSON.stringify({}) }}")
    w.http("Get approved reminders", "GET", "http://api:8000/api/reminders/approved-pending", 700, 300, retry_reads=True)
    w.node("For each approved reminder", "splitInBatches", 3, 960, 300, {"batchSize": 1, "options": {}})
    w.conditional("Reminder needs SMTP", "={{ $json.connector_mode === 'connected' }}", 1240, 390)
    w.http("Record demo reminder", "POST", "={{ 'http://api:8000/api/reminders/' + $json.id + '/dispatch' }}", 1500, 520,
           body="={{ JSON.stringify({}) }}")
    w.node("Send authorized reminder", "emailSend", 2.1, 1500, 260,
           {"fromEmail": "={{ $json.from }}", "toEmail": "={{ $json.to }}", "subject": "={{ $json.subject }}",
            "emailFormat": "text", "text": "={{ $json.body }}", "options": {}}, credentials=SMTP_CREDENTIAL)
    w.http("Acknowledge SMTP reminder", "POST",
           "={{ 'http://api:8000/api/reminders/' + $('Reminder needs SMTP').first().json.id + '/dispatch' }}", 1770, 260,
           body="={{ JSON.stringify({provider_message_id:$json.messageId || $json.message_id}) }}")
    w.link("Daily reminder schedule", "Evaluate due items")
    w.link("Receive controlled reminder run", "Evaluate due items")
    w.link("Evaluate due items", "Get approved reminders")
    w.link("Get approved reminders", "For each approved reminder")
    w.link("For each approved reminder", "Reminder needs SMTP", 1)
    w.link("Reminder needs SMTP", "Send authorized reminder", 0)
    w.link("Reminder needs SMTP", "Record demo reminder", 1)
    w.link("Send authorized reminder", "Acknowledge SMTP reminder")
    w.link("Acknowledge SMTP reminder", "For each approved reminder")
    w.link("Record demo reminder", "For each approved reminder")
    w.save()


def recovery_workflow():
    w = Workflow("recovery", "ClientLaunch | Reconcile provisioning")
    w.webhook("Receive recovery request", "clientlaunch/recover")
    w.http("Evaluate operation ledger", "POST", "={{ 'http://api:8000/api/onboardings/' + $json.body.onboarding_id + '/recover' }}", 420, 300,
           body="={{ JSON.stringify({}) }}")
    w.conditional("Safe to resume remaining steps", "={{ $json.resume_needed === true }}", 710, 300)
    w.http("Resume provisioning", "POST", "http://n8n:5678/webhook/clientlaunch/provision", 1000, 210,
           body="={{ JSON.stringify({onboarding_id:$json.onboarding_id}) }}")
    w.link("Receive recovery request", "Evaluate operation ledger")
    w.link("Evaluate operation ledger", "Safe to resume remaining steps")
    w.link("Safe to resume remaining steps", "Resume provisioning", 0)
    w.save()


def dispatch_sweeper_workflow():
    w = Workflow("dispatch_sweeper", "ClientLaunch | Sweep pending dispatches")
    w.node("Five-minute dispatch schedule", "scheduleTrigger", 1.2, 120, 300,
           {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}})
    w.http("Load pending dispatches", "GET", "http://api:8000/api/workflow-dispatches/pending", 400, 300,
           retry_reads=True)
    w.node("Cap and expand pending batch", "code", 2, 680, 300,
           {"mode": "runOnceForAllItems", "jsCode": "const rows = $input.first().json.items;\nif (!Array.isArray(rows)) throw new Error('Pending dispatch response has no items array');\nreturn rows.slice(0, 20).map((row) => ({json:row}));"})
    w.node("For each pending dispatch", "splitInBatches", 3, 960, 300,
           {"batchSize": 1, "options": {}})
    dispatch = "$('For each pending dispatch').item.json"
    w.http("Record dispatch attempt", "POST",
           f"={{{{ 'http://api:8000/api/workflow-dispatches/' + {dispatch}.id + '/attempt' }}}}", 1230, 300,
           body="={{ JSON.stringify({}) }}")
    w.conditional("Dispatch attempt authorized", "={{ $json.execute === true }}", 1500, 300)
    w.conditional("Dispatch is approval", "={{ $json.kind === 'approval' }}", 1770, 300)
    w.conditional("Dispatch is submission", "={{ $json.kind === 'submission' }}", 2040, 470)
    w.conditional("Dispatch is recovery", "={{ $json.kind === 'recovery' }}", 2310, 630)
    for kind, name, path, x, y in (
        ("approval", "Trigger approved provisioning", "provision", 2040, 150),
        ("submission", "Trigger stored submission", "submission", 2310, 350),
        ("recovery", "Trigger safe recovery", "recover", 2580, 530),
    ):
        w.http(name, "POST", f"http://n8n:5678/webhook/clientlaunch/{path}", x, y,
               body=f"={{{{ JSON.stringify({dispatch}.payload) }}}}",
               headers=[{"name": "Idempotency-Key", "value": f"={{{{ {dispatch}.id }}}}"}])
        # A non-2xx or network failure must not acknowledge the durable row or
        # stop unrelated rows in this small batch.
        w.nodes[-1]["parameters"]["options"]["response"] = {
            "response": {"fullResponse": True, "neverError": True}}
        w.nodes[-1]["onError"] = "continueRegularOutput"
    w.conditional("Webhook accepted dispatch", "={{ Number($json.statusCode) >= 200 && Number($json.statusCode) < 300 }}", 2830, 300)
    w.http("Acknowledge accepted dispatch", "POST",
           f"={{{{ 'http://api:8000/api/workflow-dispatches/' + {dispatch}.id + '/ack' }}}}", 3100, 210,
           body="={{ JSON.stringify({}) }}")
    w.link("Five-minute dispatch schedule", "Load pending dispatches")
    w.link("Load pending dispatches", "Cap and expand pending batch")
    w.link("Cap and expand pending batch", "For each pending dispatch")
    w.link("For each pending dispatch", "Record dispatch attempt", 1)
    w.link("Record dispatch attempt", "Dispatch attempt authorized")
    w.link("Dispatch attempt authorized", "Dispatch is approval", 0)
    w.link("Dispatch attempt authorized", "For each pending dispatch", 1)
    w.link("Dispatch is approval", "Trigger approved provisioning", 0)
    w.link("Dispatch is approval", "Dispatch is submission", 1)
    w.link("Dispatch is submission", "Trigger stored submission", 0)
    w.link("Dispatch is submission", "Dispatch is recovery", 1)
    w.link("Dispatch is recovery", "Trigger safe recovery", 0)
    w.link("Dispatch is recovery", "For each pending dispatch", 1)
    for name in ("Trigger approved provisioning", "Trigger stored submission", "Trigger safe recovery"):
        w.link(name, "Webhook accepted dispatch")
    w.link("Webhook accepted dispatch", "Acknowledge accepted dispatch", 0)
    w.link("Webhook accepted dispatch", "For each pending dispatch", 1)
    w.link("Acknowledge accepted dispatch", "For each pending dispatch")
    w.save()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for build in (drive_workflow, trello_workflow, error_workflow, task_sync_workflow, intake_workflow,
                  provision_workflow, submission_workflow, reminder_workflow, recovery_workflow,
                  dispatch_sweeper_workflow):
        build()
    object_id = {"type": "object", "required": ["onboarding_id"],
                 "properties": {"onboarding_id": {"type": "string"}}, "additionalProperties": False}
    contracts = {
        "drive": ({"type": "object", "required": ["onboarding_id", "request_payload", "idempotency_key", "connector_mode"],
                   "properties": {"onboarding_id": {"type": "string"}, "request_payload": {"type": "object"},
                                  "idempotency_key": {"type": "string"}, "connector_mode": {"enum": ["demo", "connected"]}}},
                  {"type": "object", "required": ["name"], "properties": {"id": {"type": "string"},
                   "external_id": {"type": "string"}, "url": {"type": "string"}, "name": {"type": "string"}}}),
        "trello": ({"type": "object", "required": ["onboarding_id", "request_payload", "idempotency_key", "connector_mode"],
                    "properties": {"onboarding_id": {"type": "string"}, "request_payload": {"type": "object"},
                                   "idempotency_key": {"type": "string"}, "connector_mode": {"enum": ["demo", "connected"]}}},
                   {"type": "object", "required": ["name", "todo_list_id"], "properties": {"id": {"type": "string"},
                    "external_id": {"type": "string"}, "url": {"type": "string"}, "name": {"type": "string"},
                    "todo_list_id": {"type": "string"}}}),
        "error": ({"type": "object", "required": ["execution", "workflow"],
                   "properties": {"execution": {"type": "object"}, "workflow": {"type": "object"}}},
                  {"type": "object", "properties": {"id": {"type": "string"}, "status": {"type": "string"}}}),
        "intake": ({"type": "object", "required": ["workspace_slug", "event_id", "external_deal_id", "client", "services", "approved_scope", "proposal_text", "account_owner_email"],
                    "properties": {"workspace_slug": {"type": "string"}, "event_id": {"type": "string"},
                                   "external_deal_id": {"type": "string"}, "client": {"type": "object"},
                                   "services": {"type": "array", "items": {"type": "string"}},
                                   "approved_scope": {"type": "string"}, "proposal_text": {"type": "string"},
                                   "timeline": {"type": "object"}, "account_owner_email": {"type": "string"}}},
                   {"type": "object", "required": ["accepted", "onboarding_id", "duplicate"],
                    "properties": {"accepted": {"type": "boolean"}, "onboarding_id": {"type": "string"},
                                   "duplicate": {"type": "boolean"}}}),
        "task_sync": (object_id, {"type": "object", "properties": {"message": {"type": "string"}}}),
        "provision": (object_id, {"type": "object", "properties": {"message": {"type": "string"}}}),
        "submission": ({"type": "object", "required": ["submission_id"],
                        "properties": {"submission_id": {"type": "string"}}, "additionalProperties": False},
                       {"type": "object", "properties": {"message": {"type": "string"}}}),
        "reminder": ({"type": "object", "properties": {}},
                     {"type": "object", "properties": {"message": {"type": "string"}}}),
        "recovery": (object_id, {"type": "object", "properties": {"message": {"type": "string"}}}),
        "dispatch_sweeper": ({"type": "object", "properties": {}},
                             {"type": "object", "properties": {"message": {"type": "string"}}}),
    }
    manifest = {"n8n_version": "2.40.7", "edition": "Community", "import_order": list(IDS),
                "credential_requirements": {
                    "CL08InternalAuth": "httpHeaderAuth: X-Internal-Key (generated locally)",
                    "__GOOGLE_DRIVE_CREDENTIAL_ID__": "Google Drive OAuth2; connected mode only",
                    "__TRELLO_CREDENTIAL_ID__": "Trello API; connected mode only",
                    "__SMTP_CREDENTIAL_ID__": "Authorized SMTP; connected mode only"},
                "workflows": [
                    {"file": f"{key}.json", "id": value,
                     "depends_on": [IDS[d] for d in ({"task_sync": ["error"], "intake": ["error"], "provision": ["drive", "trello", "task_sync", "error"],
                                                 "submission": ["task_sync", "error"], "reminder": ["error"], "recovery": ["provision", "error"],
                                                 "dispatch_sweeper": ["provision", "submission", "recovery", "error"]}.get(key, []))],
                     "input": {"intake": "signed won-deal JSON", "provision": "{onboarding_id}", "task_sync": "{onboarding_id}",
                               "submission": "{submission_id}", "recovery": "{onboarding_id}",
                                "drive": "claim response", "trello": "claim response", "reminder": "daily schedule or authenticated POST /webhook/clientlaunch/reminder-run with {}",
                               "dispatch_sweeper": "schedule", "error": "n8n error payload"}[key],
                     "output": "n8n execution record and persisted API state",
                     "input_schema": contracts[key][0], "output_schema": contracts[key][1]}
                    for key, value in IDS.items()]}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
