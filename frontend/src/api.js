// Thin fetch wrapper: attaches the JWT and centralises error handling.
const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export function getToken() {
  return localStorage.getItem("access");
}
export function setTokens({ access, refresh }) {
  if (access) localStorage.setItem("access", access);
  if (refresh) localStorage.setItem("refresh", refresh);
}
export function clearTokens() {
  localStorage.removeItem("access");
  localStorage.removeItem("refresh");
}

async function request(path, { method = "GET", body, isForm } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let payload = body;
  if (body && !isForm) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}${path}`, { method, headers, body: payload });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = JSON.stringify(await res.json());
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  base: BASE,
  register: (data) => request("/api/auth/register/", { method: "POST", body: data }),
  login: (data) => request("/api/auth/login/", { method: "POST", body: data }),
  me: () => request("/api/auth/me/"),

  groups: () => request("/api/groups/"),
  createGroup: (name) => request("/api/groups/", { method: "POST", body: { name } }),
  group: (id) => request(`/api/groups/${id}/`),
  balances: (id) => request(`/api/groups/${id}/balances/`),
  ledger: (id, mid) => request(`/api/groups/${id}/members/${mid}/ledger/`),
  explain: (id, mid) => request(`/api/groups/${id}/members/${mid}/explain/`),

  expenses: (groupId) => request(`/api/expenses/?group=${groupId}`),
  addExpense: (payload) =>
    request("/api/expenses/", { method: "POST", body: payload }),
  settlements: (groupId) => request(`/api/settlements/?group=${groupId}`),
  addSettlement: (payload) =>
    request("/api/settlements/", { method: "POST", body: payload }),
  addMember: (groupId, name, joined_at) =>
    request(`/api/groups/${groupId}/add_member/`, {
      method: "POST",
      body: { name, joined_at },
    }),
  memberLeave: (groupId, memberId, left_at) =>
    request(`/api/groups/${groupId}/members/${memberId}/leave/`, {
      method: "POST",
      body: { left_at },
    }),

  upload: (groupId, file) => {
    const fd = new FormData();
    fd.append("group", groupId);
    fd.append("file", file);
    return request("/api/import/upload/", { method: "POST", body: fd, isForm: true });
  },
  batch: (id) => request(`/api/import/batches/${id}/`),
  resolveRow: (rowId, resolution) =>
    request(`/api/import/rows/${rowId}/`, { method: "PATCH", body: { resolution } }),
  commit: (batchId) =>
    request(`/api/import/batches/${batchId}/commit/`, { method: "POST" }),
};
