import { Link, Outlet } from "react-router-dom";
import { useAuth } from "./auth";

export default function App() {
  const { user, logout } = useAuth();
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          Shared Expenses
        </Link>
        <div className="spacer" />
        <span className="muted">{user?.username}</span>
        <button className="link" onClick={logout}>
          Log out
        </button>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </div>
  );
}
