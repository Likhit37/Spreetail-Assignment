import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

const FEATURES = [
  ["🧮", "One number per person", "Net balances and a minimal who-pays-whom."],
  ["🔎", "No magic numbers", "Every balance drills down to its source rows."],
  ["🧹", "Messy imports, handled", "Detects & explains every data problem — no silent guesses."],
];

export default function Login() {
  const { login, register } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ username: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "login") await login(form.username, form.password);
      else await register(form.username, form.email, form.password);
      nav("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center">
      <div className="auth-wrap">
        <div className="auth-hero">
          <div className="brand" style={{ fontSize: "1.3rem" }}>
            <span className="logo">₹</span> SplitSmart
          </div>
          <h1 style={{ fontSize: "2.1rem", marginTop: 18 }}>
            Shared expenses, <span className="gradient-text">settled clearly</span>.
          </h1>
          <p className="muted" style={{ lineHeight: 1.6 }}>
            Track a flat's spending across changing members and currencies — and
            import a messy spreadsheet without a single silent guess.
          </p>
          <div style={{ marginTop: 20 }}>
            {FEATURES.map(([emoji, title, desc]) => (
              <div className="feature" key={title}>
                <span className="dot">{emoji}</span>
                <span>
                  <b>{title}</b>
                  <span className="muted small">{desc}</span>
                </span>
              </div>
            ))}
          </div>
        </div>

        <form className="card auth" onSubmit={submit}>
          <h2 style={{ marginBottom: 2 }}>
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h2>
          <p className="muted small" style={{ marginTop: 0 }}>
            {mode === "login"
              ? "Log in to your flat's ledger."
              : "Start tracking shared expenses."}
          </p>
          <input
            placeholder="Username"
            value={form.username}
            onChange={set("username")}
            required
          />
          {mode === "register" && (
            <input
              placeholder="Email"
              type="email"
              value={form.email}
              onChange={set("email")}
              required
            />
          )}
          <input
            placeholder="Password"
            type="password"
            value={form.password}
            onChange={set("password")}
            required
          />
          {error && <div className="error">{error}</div>}
          <button type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Log in" : "Sign up"}
          </button>
          <button
            type="button"
            className="link"
            style={{ margin: "0 auto" }}
            onClick={() => setMode(mode === "login" ? "register" : "login")}
          >
            {mode === "login"
              ? "Need an account? Sign up"
              : "Have an account? Log in"}
          </button>
        </form>
      </div>
    </div>
  );
}
