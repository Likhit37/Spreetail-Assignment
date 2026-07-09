import { useEffect, useState } from "react";
import { api } from "../api";
import Modal from "./Modal";

// A member is active on `date` if it's within their join/leave window.
const activeOn = (m, date) =>
  (!m.joined_at || date >= m.joined_at) && (!m.left_at || date <= m.left_at);

const TYPES = [
  ["equal", "Equal", "Split evenly among the people you pick."],
  ["percentage", "Percentage", "Each person's % (weights; need not sum to 100)."],
  ["share", "Share", "Ratio, e.g. 2:1:1."],
  ["unequal", "Unequal", "Exact ₹ amounts that sum to the total."],
];

export default function AddExpenseModal({ group, onClose, onSaved }) {
  const members = group.members;
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({
    date: today,
    description: "",
    paid_by: members[0]?.id || "",
    amount_original: "",
    currency: "INR",
    split_type: "equal",
  });
  const [checked, setChecked] = useState(() =>
    members.filter((m) => activeOn(m, today)).map((m) => m.id)
  );
  const [details, setDetails] = useState({}); // memberId -> value
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const weighted = f.split_type !== "equal";

  // When the date changes, keep the equal-split selection to active members.
  useEffect(() => {
    setChecked((c) => c.filter((id) => activeOn(members.find((m) => m.id === id), f.date)));
  }, [f.date, members]);

  function toggle(id) {
    setChecked((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  }
  function setDetail(id, v) {
    setDetails((d) => ({ ...d, [id]: v }));
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = {
        group: group.id,
        date: f.date,
        description: f.description,
        paid_by: Number(f.paid_by),
        amount_original: f.amount_original,
        currency: f.currency,
        split_type: f.split_type,
      };
      if (weighted) {
        payload.details = Object.fromEntries(
          Object.entries(details).filter(
            ([id, v]) =>
              v !== "" && v != null && activeOn(members.find((m) => m.id === Number(id)), f.date)
          )
        );
      } else {
        payload.participants = checked;
      }
      await api.addExpense(payload);
      onSaved();
    } catch (err) {
      setError(err.message.replace(/^\d+:\s*/, "").replace(/[{}"]|detail:?/g, ""));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Add expense" onClose={onClose}>
      <form onSubmit={submit} style={{ display: "grid", gap: 10, marginTop: 8 }}>
        <input placeholder="Description" value={f.description} onChange={set("description")} required />
        <div className="row" style={{ margin: 0 }}>
          <input type="date" value={f.date} onChange={set("date")} required />
          <select value={f.currency} onChange={set("currency")} style={{ maxWidth: 100 }}>
            <option>INR</option>
            <option>USD</option>
          </select>
        </div>
        <div className="row" style={{ margin: 0 }}>
          <input
            type="number"
            step="0.01"
            placeholder="Amount"
            value={f.amount_original}
            onChange={set("amount_original")}
            required
          />
          <select value={f.paid_by} onChange={set("paid_by")}>
            {members.map((m) => (
              <option key={m.id} value={m.id}>
                paid by {m.name}
              </option>
            ))}
          </select>
        </div>

        <div className="row" style={{ margin: 0, gap: 4, flexWrap: "wrap" }}>
          {TYPES.map(([val, label]) => (
            <button
              type="button"
              key={val}
              className={f.split_type === val ? "tab active" : "tab"}
              onClick={() => setF({ ...f, split_type: val })}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="faint small" style={{ margin: 0 }}>
          {TYPES.find((t) => t[0] === f.split_type)[2]}
        </p>

        <div style={{ display: "grid", gap: 6 }}>
          {members.map((m) => {
            const active = activeOn(m, f.date);
            return (
              <label
                key={m.id}
                className="row"
                style={{ margin: 0, gap: 8, opacity: active ? 1 : 0.4 }}
              >
                {weighted ? (
                  <>
                    <span style={{ minWidth: 90 }}>{m.name}</span>
                    <input
                      type="number"
                      step="0.01"
                      disabled={!active}
                      placeholder={f.split_type === "unequal" ? "₹" : "value"}
                      value={details[m.id] ?? ""}
                      onChange={(e) => setDetail(m.id, e.target.value)}
                    />
                  </>
                ) : (
                  <>
                    <input
                      type="checkbox"
                      style={{ width: "auto" }}
                      disabled={!active}
                      checked={checked.includes(m.id)}
                      onChange={() => toggle(m.id)}
                    />
                    <span>{m.name}</span>
                  </>
                )}
                {!active && <span className="chip">not in flat on this date</span>}
              </label>
            );
          })}
        </div>

        {error && <div className="error">{error}</div>}
        <button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Add expense"}
        </button>
      </form>
    </Modal>
  );
}
