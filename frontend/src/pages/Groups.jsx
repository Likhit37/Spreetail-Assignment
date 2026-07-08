import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function Groups() {
  const [groups, setGroups] = useState([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const load = () => api.groups().then(setGroups).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function create(e) {
    e.preventDefault();
    if (!name.trim()) return;
    await api.createGroup(name.trim());
    setName("");
    load();
  }

  return (
    <div>
      <h1>Your groups</h1>
      {error && <div className="error">{error}</div>}
      <form className="row" onSubmit={create}>
        <input
          placeholder="New group name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit">Create</button>
      </form>
      <ul className="list">
        {groups.map((g) => (
          <li key={g.id} className="card">
            <Link to={`/groups/${g.id}`}>{g.name}</Link>
            <span className="muted">{g.members?.length || 0} members</span>
          </li>
        ))}
        {groups.length === 0 && <p className="muted">No groups yet. Create one.</p>}
      </ul>
    </div>
  );
}
