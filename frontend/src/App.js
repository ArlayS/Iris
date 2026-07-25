import { useEffect, useState } from "react";
import "@/App.css";
import "@/MentalHealth.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { api } from "./api/client";
import AppShell from "./components/AppShell";
import AdminDashboardPage from "./pages/AdminDashboardPage";
import DashboardPage from "./pages/DashboardPage";
import HelperProfilePage from "./pages/HelperProfilePage";
import LoginPage from "./pages/LoginPage";
import NewTicketPage from "./pages/NewTicketPage";
import TicketWorkspacePage from "./pages/TicketWorkspacePage";


function AuthenticatedApp({ helper, isAdmin, theme, toggleTheme }) {
  const [tickets, setTickets] = useState([]);
  const [stats, setStats] = useState({ active_count: 0, archived_count: 0, total_messages: 0 });

  const refreshDashboard = async () => {
    const [ticketsResponse, statsResponse] = await Promise.all([api.get("/tickets"), api.get("/tickets/stats")]);
    setTickets(ticketsResponse.data);
    setStats(statsResponse.data);
  };

  useEffect(() => {
    refreshDashboard().catch(() => undefined);
  }, []);

  const updateTicket = (ticket) => {
    setTickets((current) => [ticket, ...current.filter((item) => item.id !== ticket.id)]);
    api.get("/tickets/stats")
      .then((response) => setStats(response.data))
      .catch(() => undefined);
  };

  const logout = async () => {
    await api.post("/auth/logout");
    window.location.assign("/");
  };

  return (
    <AppShell helper={helper} tickets={tickets} onLogout={logout} isAdmin={isAdmin} theme={theme} onToggleTheme={toggleTheme}>
      <Routes>
        <Route path="/" element={<DashboardPage stats={stats} tickets={tickets} />} />
        <Route path="/new" element={<NewTicketPage onCreated={updateTicket} />} />
        <Route path="/tickets/:ticketId" element={<TicketWorkspacePage onTicketUpdate={updateTicket} isAdmin={isAdmin} helper={helper} />} />
        <Route path="/archives" element={<DashboardPage stats={stats} tickets={tickets.filter((ticket) => ticket.status === "archived")} />} />
        <Route path="/admin" element={<AdminDashboardPage />} />
        <Route path="/profile" element={<HelperProfilePage helper={helper} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}

function App() {
  const [session, setSession] = useState(null);
  const [theme, setTheme] = useState(() => localStorage.getItem("iris-theme") || "light");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("iris-theme", theme);
  }, [theme]);

  useEffect(() => {
    api.get("/auth/session")
      .then((response) => setSession(response.data))
      .catch(() => setSession({ authenticated: false }));
  }, []);

  if (!session) {
    return <div className="app-loading" data-testid="application-loading">Initialisation d’Iris…</div>;
  }

  return (
    <div className="App" data-testid="iris-app" data-theme={theme}>
      <BrowserRouter>
        {session.authenticated ? <AuthenticatedApp helper={session.helper} isAdmin={session.is_admin} theme={theme} toggleTheme={() => setTheme((current) => current === "light" ? "dark" : "light")} /> : <LoginPage />}
        <Toaster theme="light" position="bottom-right" />
      </BrowserRouter>
    </div>
  );
}

export default App;
