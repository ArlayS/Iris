import { useEffect, useState } from "react";
import "@/App.css";
import "@/MentalHealth.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { api } from "./api/client";
import AppShell from "./components/AppShell";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import NewTicketPage from "./pages/NewTicketPage";
import TicketWorkspacePage from "./pages/TicketWorkspacePage";


function AuthenticatedApp({ helper }) {
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

  const createQuickCase = async () => {
    const response = await api.post("/tickets/demo", {
      name: "Nouvelle personne",
      reason: "Demande d’écoute à préciser",
      priority: "routine",
      follow_up_status: "à écouter",
    });
    updateTicket(response.data);
    return response.data;
  };

  const logout = async () => {
    await api.post("/auth/logout");
    window.location.assign("/");
  };

  return (
    <AppShell helper={helper} tickets={tickets} onLogout={logout} isDemo={helper.mode === "demo"}>
      <Routes>
        <Route path="/" element={<DashboardPage stats={stats} tickets={tickets} isDemo={helper.mode === "demo"} onQuickCreate={createQuickCase} />} />
        <Route path="/new" element={<NewTicketPage onCreated={updateTicket} isDemo={helper.mode === "demo"} />} />
        <Route path="/tickets/:ticketId" element={<TicketWorkspacePage onTicketUpdate={updateTicket} isDemo={helper.mode === "demo"} />} />
        <Route path="/archives" element={<DashboardPage stats={stats} tickets={tickets.filter((ticket) => ticket.status === "archived")} isDemo={helper.mode === "demo"} onQuickCreate={createQuickCase} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}

function App() {
  const [session, setSession] = useState(null);

  useEffect(() => {
    api.get("/auth/session")
      .then((response) => setSession(response.data))
      .catch(() => setSession({ authenticated: false }));
  }, []);

  if (!session) {
    return <div className="app-loading" data-testid="application-loading">Initialisation d’Iris…</div>;
  }

  return (
    <div className="App">
      <BrowserRouter>
        {session.authenticated ? <AuthenticatedApp helper={session.helper} /> : <LoginPage />}
        <Toaster theme="light" position="bottom-right" />
      </BrowserRouter>
    </div>
  );
}

export default App;
