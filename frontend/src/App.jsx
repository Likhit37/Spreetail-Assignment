import { Link, Outlet } from "react-router-dom";
import { useAuth } from "./auth";
import { Avatar } from "./ui";

export default function App() {
  const { user, logout } = useAuth();
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="logo">₹</span> SplitSmart
        </Link>
        <div className="spacer" />
        {user && (
          <>
            <Avatar name={user.username} sm />
            <span className="muted small">{user.username}</span>
            <button className="link" onClick={logout}>
              Log out
            </button>
          </>
        )}
      </header>
      <main className="container">
        <Outlet />
      </main>
    </div>
  );
}
