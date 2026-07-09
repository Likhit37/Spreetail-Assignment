import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Avatar } from "../ui";

export default function Groups() {
  const [groups, setGroups] = useState(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api.groups().then(setGroups).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function create(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.createGroup(name.trim());
      setName("");
      await load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="row between wrap">
        <div>
          <h1>Your groups</h1>
          <p className="muted" style={{ marginTop: -6 }}>
            A group is a household or trip whose members can change over time.
          </p>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <form className="card row" onSubmit={create}>
        <input
          placeholder="e.g. Flat 4B, Goa trip…"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit" disabled={busy || !name.trim()}>
          + Create group
        </button>
      </form>

      {groups === null && <p className="muted">Loading…</p>}

      {groups && groups.length === 0 && (
        <div className="card empty">
          <div className="emoji">🏡</div>
          <h3>No groups yet</h3>
          <p className="muted">Create your first group above to start tracking.</p>
        </div>
      )}

      {groups && groups.length > 0 && (
        <div className="stat-grid" style={{ marginTop: 8 }}>
          {groups.map((g) => (
            <Link
              key={g.id}
              to={`/groups/${g.id}`}
              className="card hover-lift"
              style={{ margin: 0 }}
            >
              <div className="row" style={{ margin: 0, gap: 12 }}>
                <Avatar name={g.name} />
                <div>
                  <div style={{ fontWeight: 700, color: "var(--text)" }}>
                    {g.name}
                  </div>
                  <div className="muted small">
                    {g.members?.length || 0} member
                    {(g.members?.length || 0) === 1 ? "" : "s"}
                  </div>
                </div>
              </div>
              {g.members?.length > 0 && (
                <div
                  className="row"
                  style={{ margin: "12px 0 0", gap: 4, flexWrap: "wrap" }}
                >
                  {g.members.slice(0, 6).map((m) => (
                    <Avatar key={m.id} name={m.name} sm />
                  ))}
                  {g.members.length > 6 && (
                    <span className="chip">+{g.members.length - 6}</span>
                  )}
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
