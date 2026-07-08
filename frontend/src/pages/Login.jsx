import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Login() {
  const { login, register } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ username: "", email: "", password: "" });
  const [error, setError] = useState("");

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      if (mode === "login") await login(form.username, form.password);
      else await register(form.username, form.email, form.password);
      nav("/");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="center">
      <form className="card auth" onSubmit={submit}>
        <h1>Shared Expenses</h1>
        <p className="muted">
          {mode === "login" ? "Log in to your flat" : "Create an account"}
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
        <button type="submit">{mode === "login" ? "Log in" : "Sign up"}</button>
        <button
          type="button"
          className="link"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? "Need an account? Sign up" : "Have an account? Log in"}
        </button>
      </form>
    </div>
  );
}
