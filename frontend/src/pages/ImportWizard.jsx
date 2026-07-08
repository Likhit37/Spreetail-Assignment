import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api";

const SEV = { blocker: "sev-blocker", warning: "sev-warning", info: "sev-info" };

export default function ImportWizard() {
  const { id } = useParams();
  const [file, setFile] = useState(null);
  const [batch, setBatch] = useState(null);
  const [report, setReport] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [resolutions, setResolutions] = useState({}); // rowId -> resolution

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
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const flagged = batch?.rows.filter((r) => r.anomalies.length > 0) || [];

  return (
    <div>
      <div className="row between">
        <h1>Import spreadsheet</h1>
        <Link className="link" to={`/groups/${id}`}>
          ← Back to group
        </Link>
      </div>

      <form className="row" onSubmit={upload}>
        <input
          type="file"
          accept=".xlsx,.csv"
          onChange={(e) => setFile(e.target.files[0])}
        />
        <button type="submit" disabled={busy || !file}>
          {busy ? "Analysing…" : "Upload & analyse"}
        </button>
      </form>
      {error && <div className="error">{error}</div>}

      {report && (
        <div className="card summary">
          <strong>{report.total_rows}</strong> rows ·{" "}
          <strong>{report.rows_with_anomalies}</strong> with issues ·{" "}
          <strong>{report.distinct_anomaly_types}</strong> anomaly types
          {result && (
            <span className="pos">
              {"  "}✓ Committed: {result.committed.expenses} expenses,{" "}
              {result.committed.settlements} settlements, {result.committed.skipped}{" "}
              skipped
            </span>
          )}
        </div>
      )}

      {batch && !result && (
        <>
          <p className="muted">
            Review the issues below, resolve any blockers, then commit. Nothing is
            saved until you commit.
          </p>
          <table className="card wide">
            <thead>
              <tr>
                <th>Row</th>
                <th>Description</th>
                <th>Kind</th>
                <th>Anomalies</th>
                <th>Resolve</th>
              </tr>
            </thead>
            <tbody>
              {flagged.map((row) => (
                <tr key={row.id}>
                  <td>{row.row_number}</td>
                  <td>{row.raw.description}</td>
                  <td>{row.kind}</td>
                  <td>
                    {row.anomalies.map((a, i) => (
                      <div key={i} className={`anomaly ${SEV[a.severity]}`}>
                        <strong>{a.code}</strong>: {a.message}
                        <div className="muted small">→ {a.action}</div>
                      </div>
                    ))}
                  </td>
                  <td>
                    {(row.kind === "duplicate" || row.kind === "invalid") && (
                      <label className="small">
                        <input
                          type="checkbox"
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
          <button onClick={commit} disabled={busy}>
            {busy ? "Committing…" : "Commit import"}
          </button>
        </>
      )}

      {result && (
        <div className="card">
          <h3>Import report</h3>
          <table className="wide">
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
                  <td>{f.row}</td>
                  <td>{f.code}</td>
                  <td className={SEV[f.severity]}>{f.severity}</td>
                  <td>{f.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Link className="button" to={`/groups/${id}`}>
            View balances
          </Link>
        </div>
      )}
    </div>
  );
}
