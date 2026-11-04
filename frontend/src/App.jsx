import React, { useRef, useState } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard.jsx';
import Landing from './pages/Landing.jsx';

function LandingRoute({ toast }) {
  const navigate = useNavigate();
  return <Landing onEnter={() => navigate('/dashboard')} toast={toast} />;
}

function DashboardRoute({ toast }) {
  const navigate = useNavigate();
  return <Dashboard onExit={() => navigate('/')} toast={toast} />;
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
        <Route path="/" element={<LandingRoute toast={toast} />} />
        <Route path="/dashboard" element={<DashboardRoute toast={toast} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      {msg && <div className="toast" role="status">{msg}</div>}
    </>
  );
}
