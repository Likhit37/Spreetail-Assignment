import { createContext, useContext, useEffect, useState } from "react";
import { api, clearTokens, getToken, setTokens } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (getToken()) {
      api.me().then(setUser).catch(clearTokens).finally(() => setReady(true));
    } else {
      setReady(true);
    }
  }, []);

  async function login(username, password) {
    const tokens = await api.login({ username, password });
    setTokens(tokens);
    setUser(await api.me());
  }

  async function register(username, email, password) {
    await api.register({ username, email, password });
    await login(username, password);
  }

  function logout() {
    clearTokens();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, ready, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
