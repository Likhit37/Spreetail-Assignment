import { useState } from "react";
import { api } from "../api";
import { Avatar } from "../ui";
import Modal from "./Modal";

export default function MembersModal({ group, onClose, onSaved }) {
  const [name, setName] = useState("");
  const [joined, setJoined] = useState("");
  const [leaveFor, setLeaveFor] = useState(null); // memberId
  const [leftAt, setLeftAt] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function add(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api.addMember(group.id, name.trim(), joined || null);
      setName("");
      setJoined("");
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function markLeft(memberId) {
    if (!leftAt) return;
    setBusy(true);
    try {
      await api.memberLeave(group.id, memberId, leftAt);
      setLeaveFor(null);
      setLeftAt("");
      onSaved();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Manage members" onClose={onClose}>
      <p className="muted small" style={{ marginTop: 4 }}>
        Membership can change over time — set a join date, or mark when someone
        left. Expenses only split among members active on the expense's date.
      </p>

      <div style={{ display: "grid", gap: 6, margin: "10px 0" }}>
        {group.members.map((m) => (
          <div key={m.id} className="row between" style={{ margin: 0 }}>
            <span className="row" style={{ margin: 0, gap: 8 }}>
              <Avatar name={m.name} sm />
              {m.name}
              {m.is_guest && <span className="chip">guest</span>}
            </span>
            {leaveFor === m.id ? (
              <span className="row" style={{ margin: 0, gap: 6 }}>
                <input
                  type="date"
                  value={leftAt}
                  onChange={(e) => setLeftAt(e.target.value)}
                  style={{ maxWidth: 150 }}
                />
                <button className="ghost" onClick={() => markLeft(m.id)} disabled={busy}>
                  Save
                </button>
              </span>
            ) : (
              <button className="link" onClick={() => setLeaveFor(m.id)}>
                mark left
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="divider" />
      <form onSubmit={add} style={{ display: "grid", gap: 8 }}>
        <b className="small">Add a member</b>
        <div className="row" style={{ margin: 0 }}>
          <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <input
            type="date"
            title="Join date (optional)"
            value={joined}
            onChange={(e) => setJoined(e.target.value)}
            style={{ maxWidth: 160 }}
          />
        </div>
        {error && <div className="error">{error}</div>}
        <button type="submit" disabled={busy || !name.trim()}>
          + Add member
        </button>
      </form>
    </Modal>
  );
}
