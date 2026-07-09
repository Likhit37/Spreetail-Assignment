import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { Avatar, inr } from "../ui";

export default function GroupDetail() {
  const { id } = useParams();
  const [group, setGroup] = useState(null);
  const [balances, setBalances] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [settlements, setSettlements] = useState([]);
  const [tab, setTab] = useState("balances");
  const [drill, setDrill] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.group(id).then(setGroup).catch((e) => setError(e.message));
    api.balances(id).then(setBalances).catch((e) => setError(e.message));
    api.expenses(id).then(setExpenses).catch(() => {});
    api.settlements(id).then(setSettlements).catch(() => {});
  }, [id]);

  const stats = useMemo(() => {
    const total = expenses.reduce((s, e) => s + Number(e.amount_inr), 0);
    const currencies = [...new Set(expenses.map((e) => e.currency))];
    return {
      total,
      currencies,
      members: group?.members?.length || 0,
      txns: expenses.length + settlements.length,
    };
  }, [expenses, settlements, group]);

  const maxAbs = useMemo(
    () =>
      Math.max(1, ...(balances?.net || []).map((b) => Math.abs(Number(b.net_inr)))),
    [balances]
  );

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
      <div className="row between wrap">
        <div className="row" style={{ margin: 0, gap: 12 }}>
          <Avatar name={group.name} />
          <h1 style={{ margin: 0 }}>{group.name}</h1>
        </div>
        <Link className="button" to={`/groups/${id}/import`}>
          📥 Import spreadsheet
        </Link>
      </div>

      <div className="stat-grid">
        <Stat label="Total spent" value={inr(stats.total)} sub={`${expenses.length} expenses`} />
        <Stat label="Members" value={stats.members} sub="in this group" />
        <Stat label="Transactions" value={stats.txns} sub={`${settlements.length} settlements`} />
        <Stat
          label="Currencies"
          value={stats.currencies.length || "—"}
          sub={stats.currencies.join(" · ") || "no data"}
        />
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
            {balances.net.length === 0 && (
              <p className="muted small">No balances yet — import or add expenses.</p>
            )}
            {balances.net.map((b) => {
              const v = Number(b.net_inr);
              const w = (Math.abs(v) / maxAbs) * 100;
              const color = v < 0 ? "var(--neg)" : v > 0 ? "var(--pos)" : "var(--faint)";
              return (
                <div className="bal-row" key={b.member} onClick={() => openDrill(b.member)}>
                  <div className="who">
                    <Avatar name={b.name} sm />
                    {b.name}
                  </div>
                  <div className="bal-bar">
                    <span
                      style={{
                        width: `${w}%`,
                        background: color,
                        left: v < 0 ? "auto" : 0,
                        right: v < 0 ? 0 : "auto",
                        opacity: 0.85,
                      }}
                    />
                  </div>
                  <div className="bal-amt" style={{ color }}>
                    {v > 0 ? "+" : ""}
                    {inr(v)}
                  </div>
                </div>
              );
            })}
            <p className="muted small" style={{ marginTop: 10 }}>
              <span className="pos">Green</span> is owed money ·{" "}
              <span className="neg">red</span> owes · click a row for the breakdown.
            </p>
          </div>

          <div className="card">
            <h3>Who pays whom</h3>
            {balances.simplified.length === 0 ? (
              <div className="empty" style={{ padding: 26 }}>
                <div className="emoji">🎉</div>
                Everyone is settled up.
              </div>
            ) : (
              balances.simplified.map((t, i) => (
                <div className="transfer" key={i}>
                  <Avatar name={t.from_name} sm />
                  <span>{t.from_name}</span>
                  <span className="arrow">→</span>
                  <Avatar name={t.to_name} sm />
                  <span>{t.to_name}</span>
                  <span className="amt">{inr(t.amount)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {tab === "expenses" && (
        <div className="card wide">
          {expenses.length === 0 ? (
            <div className="empty">
              <div className="emoji">🧾</div>
              No expenses yet.
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Description</th>
                  <th>Paid by</th>
                  <th style={{ textAlign: "right" }}>Amount</th>
                  <th>Split</th>
                </tr>
              </thead>
              <tbody>
                {expenses.map((e) => (
                  <tr key={e.id}>
                    <td className="muted small tabular">{e.date}</td>
                    <td>{e.description}</td>
                    <td>
                      <span className="row" style={{ margin: 0, gap: 7 }}>
                        <Avatar name={e.paid_by_name} sm />
                        {e.paid_by_name}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }} className="tabular">
                      {inr(e.amount_inr)}
                      {e.currency !== "INR" && (
                        <div>
                          <span className="chip usd">
                            {e.amount_original} {e.currency}
                          </span>
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="chip accent">{e.split_type}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {drill && (
        <div className="modal" onClick={() => setDrill(null)}>
          <div className="card modal-body" onClick={(e) => e.stopPropagation()}>
            {drill.loading ? (
              <p className="muted">Loading breakdown…</p>
            ) : (
              <>
                <div className="row" style={{ margin: 0, gap: 12 }}>
                  <Avatar name={drill.ledger.member} />
                  <div>
                    <h3 style={{ margin: 0 }}>{drill.ledger.member}</h3>
                    <span
                      className={Number(drill.ledger.net_inr) < 0 ? "neg" : "pos"}
                      style={{ fontWeight: 700 }}
                    >
                      {inr(drill.ledger.net_inr)} · {drill.ledger.interpretation}
                    </span>
                  </div>
                </div>

                <blockquote className="explain">
                  {drill.explain.text}
                  <span className="chip" style={{ marginLeft: 8 }}>
                    {drill.explain.source === "llm" ? "🤖 AI" : "rule-based"}
                  </span>
                </blockquote>

                <Section title={`Paid for the group (${drill.ledger.paid_expenses.length})`}>
                  {drill.ledger.paid_expenses.map((p) => (
                    <div className="ledger-line" key={p.expense_id}>
                      <span>
                        <span className="muted small">{p.date}</span> {p.description}
                      </span>
                      <span className="pos tabular">{inr(p.amount_inr)}</span>
                    </div>
                  ))}
                </Section>

                <Section title={`Their share (${drill.ledger.owed_shares.length})`}>
                  {drill.ledger.owed_shares.map((o) => (
                    <div className="ledger-line" key={o.expense_id}>
                      <span>
                        <span className="muted small">{o.date}</span> {o.description}
                      </span>
                      <span className="neg tabular">{inr(o.share_inr)}</span>
                    </div>
                  ))}
                </Section>

                {drill.ledger.settlements.length > 0 && (
                  <Section title={`Settlements (${drill.ledger.settlements.length})`}>
                    {drill.ledger.settlements.map((s) => (
                      <div className="ledger-line" key={s.settlement_id}>
                        <span>
                          <span className="muted small">{s.date}</span> {s.direction}{" "}
                          ({s.counterparty})
                        </span>
                        <span className="tabular">{inr(s.amount_inr)}</span>
                      </div>
                    ))}
                  </Section>
                )}

                <button style={{ marginTop: 14 }} onClick={() => setDrill(null)}>
                  Close
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      <div className="sub">{sub}</div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginTop: 14 }}>
      <h4 className="muted" style={{ fontSize: "0.8rem", textTransform: "uppercase" }}>
        {title}
      </h4>
      {children}
    </div>
  );
}
