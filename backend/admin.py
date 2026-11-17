from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from auth import require_admin
from schemas import KeyCreate, OrgCreate, QuotaUpdate
from store import Store

ADMIN_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Weather Decision Admin</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
         background: #071016; color: #d8eee7; }
  header { padding: 18px 24px; border-bottom: 1px solid #1d3a3c; }
  h1 { margin: 0; font-size: 16px; letter-spacing: .08em; text-transform: uppercase; }
  main { max-width: 1100px; margin: 0 auto; padding: 24px; }
  section { border: 1px solid #1d3a3c; background: #0b1b20; padding: 16px; margin: 0 0 16px; }
  h2 { font-size: 12px; letter-spacing: .12em; text-transform: uppercase; color: #7fd9bf; }
  input, button { font: inherit; background: #0f272c; color: #d8eee7;
                  border: 1px solid #2a4a4a; padding: 8px 10px; border-radius: 4px; }
  button { cursor: pointer; background: #9deccf; color: #08201e; font-weight: 700; }
  table { width: 100%; border-collapse: collapse; margin-top: 10px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid #163034; vertical-align: top; }
  th { color: #7f9f97; font-weight: 500; }
  .muted { color: #6e8d86; }
  .key { color: #ffe08a; word-break: break-all; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  #token { width: 280px; }
</style>
</head>
<body>
<header><h1>Weather Decision / Admin</h1></header>
<main>
  <section>
    <div class="row">
      <label for="token">Admin token</label>
      <input id="token" type="password" placeholder="X-Admin-Token" />
      <button onclick="saveToken()">Connect</button>
      <span id="status" class="muted"></span>
    </div>
  </section>

  <section>
    <h2>Create organization</h2>
    <div class="row">
      <input id="org-name" placeholder="Organization name" />
      <input id="org-quota" type="number" value="100000" min="0" />
      <button onclick="createOrg()">Create</button>
    </div>
    <div id="new-org-key" class="key"></div>
  </section>

  <section>
    <h2>Organizations &amp; usage</h2>
    <table>
      <thead><tr><th>Name</th><th>Used</th><th>Quota</th><th>Actions</th></tr></thead>
      <tbody id="orgs"></tbody>
    </table>
  </section>

  <section>
    <h2>Top tools (30 days)</h2>
    <table>
      <thead><tr><th>Tool</th><th>Units</th></tr></thead>
      <tbody id="tools"></tbody>
    </table>
  </section>
</main>
<script>
const $ = (id) => document.getElementById(id);
let token = sessionStorage.getItem("adminToken") || "";
if (token) $("token").value = token;

function saveToken() {
  token = $("token").value.trim();
  sessionStorage.setItem("adminToken", token);
  load();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", "X-Admin-Token": token };
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

async function load() {
  $("status").textContent = "loading…";
  try {
    const data = await api("/admin/api/overview");
    $("status").textContent = `${data.orgs.length} orgs · ${data.sites} sites · ${data.api_keys} keys`;
    $("orgs").innerHTML = data.orgs.map((org) => `
      <tr>
        <td>${escapeHtml(org.name)}<div class="muted">${escapeHtml(org.id)}</div></td>
        <td>${org.used}</td>
        <td>${org.monthly_quota}</td>
        <td>
          <button onclick="createKey('${org.id}')">New key</button>
          <button onclick="setQuota('${org.id}', ${org.monthly_quota})">Quota</button>
          <button onclick="listKeys('${org.id}')">Keys</button>
        </td>
      </tr>`).join("");
    $("tools").innerHTML = data.top_tools.map((row) => `
      <tr><td>${escapeHtml(row.tool)}</td><td>${row.units}</td></tr>`).join("");
    if (!data.top_tools.length) $("tools").innerHTML = '<tr><td colspan="2" class="muted">No usage yet</td></tr>';
  } catch (error) {
    $("status").textContent = "error: " + error.message;
  }
}

async function createOrg() {
  const name = $("org-name").value.trim();
  const quota = Number($("org-quota").value || 0);
  if (!name) return;
  const org = await api("/admin/api/orgs", {
    method: "POST", body: JSON.stringify({ name, monthly_quota: quota })
  });
  const key = await api(`/admin/api/orgs/${org.id}/keys`, {
    method: "POST", body: JSON.stringify({ name: "default" })
  });
  $("new-org-key").textContent = `API key (copy now): ${key.api_key}`;
  $("org-name").value = "";
  load();
}

async function createKey(orgId) {
  const key = await api(`/admin/api/orgs/${orgId}/keys`, {
    method: "POST", body: JSON.stringify({ name: "default" })
  });
  $("new-org-key").textContent = `API key (copy now): ${key.api_key}`;
  load();
}

async function setQuota(orgId, current) {
  const raw = prompt("Monthly quota (0 = unlimited)", String(current));
  if (raw === null) return;
  await api(`/admin/api/orgs/${orgId}/quota`, {
    method: "POST", body: JSON.stringify({ monthly_quota: Number(raw) })
  });
  load();
}

async function listKeys(orgId) {
  const keys = await api(`/admin/api/orgs/${orgId}/keys`);
  const lines = keys.map((key) =>
    `${key.prefix}… ${key.name} ${key.revoked_at ? "REVOKED" : "active"}`
  );
  alert(lines.join("\\n") || "No keys");
}

load();
</script>
</body>
</html>"""


def register_admin(app: FastAPI) -> None:
    @app.get("/admin", response_class=HTMLResponse)
    async def admin_page() -> str:
        return ADMIN_HTML

    @app.get("/admin/api/overview", dependencies=[Depends(require_admin)])
    async def admin_overview(request: Request):
        store: Store = request.app.state.store
        return await store.overview()

    @app.post("/admin/api/orgs", dependencies=[Depends(require_admin)])
    async def admin_create_org(request: Request, body: OrgCreate):
        store: Store = request.app.state.store
        org = await store.create_org(body.name, body.monthly_quota)
        return {
            "id": org.id,
            "name": org.name,
            "monthly_quota": org.monthly_quota,
        }

    @app.get(
        "/admin/api/orgs/{org_id}/keys",
        dependencies=[Depends(require_admin)],
    )
    async def admin_list_keys(request: Request, org_id: str):
        store: Store = request.app.state.store
        return await store.list_api_keys(org_id)

    @app.post(
        "/admin/api/orgs/{org_id}/keys",
        dependencies=[Depends(require_admin)],
    )
    async def admin_create_key(request: Request, org_id: str, body: KeyCreate):
        store: Store = request.app.state.store
        org = await store.get_org(org_id)
        if org is None:
            raise HTTPException(404, "Unknown organization")
        key_id, api_key = await store.create_api_key(org_id, body.name, body.scopes)
        return {"id": key_id, "api_key": api_key}

    @app.post(
        "/admin/api/orgs/{org_id}/quota",
        dependencies=[Depends(require_admin)],
    )
    async def admin_set_quota(request: Request, org_id: str, body: QuotaUpdate):
        store: Store = request.app.state.store
        org = await store.update_org_quota(org_id, body.monthly_quota)
        if org is None:
            raise HTTPException(404, "Unknown organization")
        return {"id": org.id, "monthly_quota": org.monthly_quota}

    @app.post(
        "/admin/api/keys/{key_id}/revoke",
        dependencies=[Depends(require_admin)],
    )
    async def admin_revoke_key(request: Request, key_id: str):
        store: Store = request.app.state.store
        if not await store.revoke_api_key(key_id):
            raise HTTPException(404, "Unknown API key")
        return {"status": "revoked"}
