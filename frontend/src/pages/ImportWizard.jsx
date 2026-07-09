import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api";

export default function ImportWizard() {
  const { id } = useParams();
  const [file, setFile] = useState(null);
  const [batch, setBatch] = useState(null);
  const [report, setReport] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [resolutions, setResolutions] = useState({});

  async function upload(e) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.upload(id, file);
      setBatch(res.batch);
      setReport(res.report);
      setResult(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function setRes(rowId, patch) {
    setResolutions((r) => ({ ...r, [rowId]: { ...(r[rowId] || {}), ...patch } }));
  }

  async function commit() {
    setBusy(true);
    setError("");
    try {
      for (const [rowId, resolution] of Object.entries(resolutions)) {
        await api.resolveRow(rowId, resolution);
      }
      const res = await api.commit(batch.id);
      setResult(res.result);
      setReport(res.report);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const flagged = batch?.rows.filter((r) => r.anomalies.length > 0) || [];

  return (
    <div>
      <div className="row between wrap">
        <h1>Import spreadsheet</h1>
        <Link className="link" to={`/groups/${id}`}>
          ← Back to group
        </Link>
      </div>

      {!batch && (
        <form onSubmit={upload}>
          <label className="dropzone" style={{ display: "block", cursor: "pointer" }}>
            <div style={{ fontSize: "2rem" }}>📄</div>
            <div style={{ fontWeight: 600, marginTop: 6 }}>
              {file ? file.name : "Choose a .xlsx or .csv export"}
            </div>
            <div className="muted small">
              The importer detects, surfaces, and handles every data problem —
              nothing is saved until you commit.
            </div>
            <input
              type="file"
              accept=".xlsx,.csv"
              style={{ display: "none" }}
              onChange={(e) => setFile(e.target.files[0])}
            />
          </label>
          <button type="submit" disabled={busy || !file} style={{ marginTop: 14 }}>
            {busy ? "Analysing…" : "Upload & analyse"}
          </button>
        </form>
      )}

      {error && <div className="error">{error}</div>}

      {report && (
        <>
          {result && (
            <div className="pill-ok" style={{ margin: "14px 0" }}>
              ✓ Committed {result.committed.expenses} expenses,{" "}
              {result.committed.settlements} settlements ·{" "}
              {result.committed.skipped} skipped
            </div>
          )}
          <div className="stat-grid">
            <Stat label="Rows read" value={report.total_rows} />
            <Stat label="Rows with issues" value={report.rows_with_anomalies} />
            <Stat label="Anomaly types" value={report.distinct_anomaly_types} />
          </div>
        </>
      )}

      {batch && !result && (
        <>
          <p className="muted" style={{ marginTop: 16 }}>
            Review the {flagged.length} flagged rows, resolve any blockers, then
            commit.
          </p>
          <div className="card wide">
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Description</th>
                  <th>Resolves to</th>
                  <th>Anomalies & action taken</th>
                  <th>Your call</th>
                </tr>
              </thead>
              <tbody>
                {flagged.map((row) => (
                  <tr key={row.id}>
                    <td className="muted tabular">{row.row_number}</td>
                    <td>{row.raw.description}</td>
                    <td>
                      <span className="chip">{row.kind}</span>
                    </td>
                    <td>
                      {row.anomalies.map((a, i) => (
                        <div key={i} className={`anomaly sev-${a.severity}`}>
                          <span className="row" style={{ margin: 0, gap: 6 }}>
                            <span className={`chip ${a.severity}`}>{a.severity}</span>
                            <span className="code">{a.code}</span>
                          </span>
                          <div className="small" style={{ marginTop: 3 }}>
                            {a.message}
                          </div>
                          <div className="faint small">→ {a.action}</div>
                        </div>
                      ))}
                    </td>
                    <td>
                      {(row.kind === "duplicate" || row.kind === "invalid") && (
                        <label className="small row" style={{ margin: 0, gap: 6 }}>
                          <input
                            type="checkbox"
                            style={{ width: "auto" }}
                            onChange={(e) => setRes(row.id, { keep: e.target.checked })}
                          />
                          keep anyway
                        </label>
                      )}
                      {row.anomalies.some((a) => a.code === "MISSING_PAYER") && (
                        <input
                          className="small"
                          placeholder="payer name"
                          onChange={(e) => setRes(row.id, { paid_by: e.target.value })}
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button onClick={commit} disabled={busy}>
            {busy ? "Committing…" : `Commit import (${batch.rows.length} rows)`}
          </button>
        </>
      )}

      {result && (
        <div className="card">
          <h3>Import report</h3>
          <p className="muted small">
            Every anomaly detected and the action taken — this is the audit trail.
          </p>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Anomaly</th>
                  <th>Severity</th>
                  <th>Action taken</th>
                </tr>
              </thead>
              <tbody>
                {report.findings.map((f, i) => (
                  <tr key={i}>
                    <td className="muted tabular">{f.row}</td>
                    <td className="code small">{f.code}</td>
                    <td>
                      <span className={`chip ${f.severity}`}>{f.severity}</span>
                    </td>
                    <td className="small">{f.action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Link className="button" to={`/groups/${id}`} style={{ marginTop: 14 }}>
            View balances →
          </Link>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}
