import { useState } from "react";
import { api } from "../api";
import Modal from "./Modal";

export default function SettleModal({ group, suggestion, onClose, onSaved }) {
  const members = group.members;
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({
    from_member: suggestion?.from_member || members[0]?.id || "",
    to_member: suggestion?.to_member || members[1]?.id || "",
    amount_inr: suggestion?.amount || "",
    date: today,
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.addSettlement({
        group: group.id,
        date: f.date,
        from_member: Number(f.from_member),
        to_member: Number(f.to_member),
        amount_inr: f.amount_inr,
        note: "Recorded payment",
      });
      onSaved();
    } catch (err) {
      setError(err.message.replace(/^\d+:\s*/, "").replace(/[[\]{}"]|detail:?|non_field_errors:?/g, ""));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Record a payment" onClose={onClose}>
      <p className="muted small" style={{ marginTop: 4 }}>
        Settlements move money without a split — they reduce what someone owes.
      </p>
      <form onSubmit={submit} style={{ display: "grid", gap: 10, marginTop: 4 }}>
        <div className="row" style={{ margin: 0 }}>
          <select value={f.from_member} onChange={set("from_member")}>
            {members.map((m) => (
              <option key={m.id} value={m.id}>{m.name} pays</option>
            ))}
          </select>
          <span className="arrow">→</span>
          <select value={f.to_member} onChange={set("to_member")}>
            {members.map((m) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        </div>
        <div className="row" style={{ margin: 0 }}>
          <input
            type="number"
            step="0.01"
            placeholder="Amount ₹"
            value={f.amount_inr}
            onChange={set("amount_inr")}
            required
          />
          <input type="date" value={f.date} onChange={set("date")} required />
        </div>
        {error && <div className="error">{error}</div>}
        <button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Record payment"}
        </button>
      </form>
    </Modal>
  );
}
