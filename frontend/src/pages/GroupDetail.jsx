import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";

const inr = (v) => `₹${Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;

export default function GroupDetail() {
  const { id } = useParams();
  const [group, setGroup] = useState(null);
  const [balances, setBalances] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [tab, setTab] = useState("balances");
  const [drill, setDrill] = useState(null); // {ledger, explain}
  const [error, setError] = useState("");

  useEffect(() => {
    api.group(id).then(setGroup).catch((e) => setError(e.message));
    api.balances(id).then(setBalances).catch((e) => setError(e.message));
    api.expenses(id).then(setExpenses).catch(() => {});
  }, [id]);

  async function openDrill(memberId) {
    setDrill({ loading: true });
    const [ledger, explain] = await Promise.all([
      api.ledger(id, memberId),
      api.explain(id, memberId),
    ]);
    setDrill({ ledger, explain });
  }

  if (error) return <div className="error">{error}</div>;
  if (!group) return <p className="muted">Loading…</p>;

  return (
    <div>
      <div className="row between">
        <h1>{group.name}</h1>
        <Link className="button" to={`/groups/${id}/import`}>
          Import spreadsheet
        </Link>
      </div>

      <div className="tabs">
        {["balances", "expenses"].map((t) => (
          <button
            key={t}
            className={tab === t ? "tab active" : "tab"}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "balances" && balances && (
        <div className="grid2">
          <div className="card">
            <h3>Net balance per person</h3>
            <table>
              <tbody>
                {balances.net.map((b) => (
                  <tr key={b.member}>
                    <td>
                      <button className="link" onClick={() => openDrill(b.member)}>
                        {b.name}
                      </button>
                    </td>
                    <td
                      className={
                        Number(b.net_inr) < 0 ? "neg" : Number(b.net_inr) > 0 ? "pos" : ""
                      }
                    >
                      {inr(b.net_inr)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">Click a name to see the breakdown.</p>
          </div>
          <div className="card">
            <h3>Who pays whom</h3>
            {balances.simplified.length === 0 && (
              <p className="muted">Everyone is settled up.</p>
            )}
            <ul className="list">
              {balances.simplified.map((t, i) => (
                <li key={i}>
                  <strong>{t.from_name}</strong> → <strong>{t.to_name}</strong>
                  <span className="spacer" />
                  {inr(t.amount)}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {tab === "expenses" && (
        <table className="card wide">
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th>Paid by</th>
              <th>Amount</th>
              <th>Type</th>
            </tr>
          </thead>
          <tbody>
            {expenses.map((e) => (
              <tr key={e.id}>
                <td>{e.date}</td>
                <td>{e.description}</td>
                <td>{e.paid_by_name}</td>
                <td>
                  {inr(e.amount_inr)}
                  {e.currency !== "INR" && (
                    <span className="muted small">
                      {" "}
                      ({e.amount_original} {e.currency})
                    </span>
                  )}
                </td>
                <td>{e.split_type}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {drill && (
        <div className="modal" onClick={() => setDrill(null)}>
          <div className="card modal-body" onClick={(e) => e.stopPropagation()}>
            {drill.loading ? (
              <p>Loading…</p>
            ) : (
              <>
                <h3>{drill.ledger.member}</h3>
                <p>
                  <strong>{inr(drill.ledger.net_inr)}</strong> —{" "}
                  {drill.ledger.interpretation}
                </p>
                <blockquote className="explain">
                  {drill.explain.text}
                  <span className="muted small"> ({drill.explain.source})</span>
                </blockquote>
                <h4>Paid for the group</h4>
                <ul className="small">
                  {drill.ledger.paid_expenses.map((p) => (
                    <li key={p.expense_id}>
                      {p.date} {p.description}: {inr(p.amount_inr)}
                    </li>
                  ))}
                </ul>
                <h4>Their share</h4>
                <ul className="small">
                  {drill.ledger.owed_shares.map((o) => (
                    <li key={o.expense_id}>
                      {o.date} {o.description}: {inr(o.share_inr)}
                    </li>
                  ))}
                </ul>
                {drill.ledger.settlements.length > 0 && (
                  <>
                    <h4>Settlements</h4>
                    <ul className="small">
                      {drill.ledger.settlements.map((s) => (
                        <li key={s.settlement_id}>
                          {s.date} {s.direction} {inr(s.amount_inr)} ({s.counterparty})
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                <button onClick={() => setDrill(null)}>Close</button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
