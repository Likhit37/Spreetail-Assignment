import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import App from "./App.jsx";
import Login from "./pages/Login";
import Groups from "./pages/Groups";
import GroupDetail from "./pages/GroupDetail";
import ImportWizard from "./pages/ImportWizard";
import "./index.css";

function Protected({ children }) {
  const { user, ready } = useAuth();
  if (!ready) return <div className="center">Loading…</div>;
  return user ? children : <Navigate to="/login" replace />;
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <Protected>
                <App />
              </Protected>
            }
          >
            <Route index element={<Groups />} />
            <Route path="groups/:id" element={<GroupDetail />} />
            <Route path="groups/:id/import" element={<ImportWizard />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>
);
