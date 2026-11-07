import React, { useRef, useState } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { useAuth } from './context/auth.js';
import Dashboard from './pages/Dashboard.jsx';
import Landing from './pages/Landing.jsx';
import Login from './pages/Login.jsx';
import Register from './pages/Register.jsx';

function LoadingScreen() {
  return <div className="auth-loading">Verificando sesión…</div>;
}

function LandingRoute() {
  const navigate = useNavigate();
  return (
    <Landing
      onLogin={() => navigate('/login')}
      onRegister={() => navigate('/register')}
    />
  );
}

function DashboardRoute({ toast }) {
  const navigate = useNavigate();
  const { logout } = useAuth();

  return (
    <Dashboard
      onExit={() => {
        logout();
        navigate('/', { replace: true });
      }}
      toast={toast}
    />
  );
}

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) return <LoadingScreen />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}

function PublicOnlyRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) return <LoadingScreen />;
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  const [msg, setMsg] = useState(null);
  const tm = useRef(null);

  const toast = (message) => {
    setMsg(message);
    clearTimeout(tm.current);
    tm.current = setTimeout(() => setMsg(null), 4200);
  };

  return (
    <>
      <Routes>
        <Route path="/" element={<LandingRoute />} />
        <Route
          path="/login"
          element={
            <PublicOnlyRoute>
              <Login />
            </PublicOnlyRoute>
          }
        />
        <Route
          path="/register"
          element={
            <PublicOnlyRoute>
              <Register />
            </PublicOnlyRoute>
          }
        />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <DashboardRoute toast={toast} />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      {msg && <div className="toast" role="status">{msg}</div>}
    </>
  );
}
