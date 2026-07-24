import { Archive, Bell, FolderKanban, Grid2X2, LogOut, Plus, RadioTower, Settings2 } from "lucide-react";
import { Link, NavLink } from "react-router-dom";


export default function AppShell({ children, helper, tickets, onLogout, isDemo }) {
  return (
    <div className="app-shell" data-testid="iris-application">
      <aside className="sidebar nano-sidebar" data-testid="main-navigation">
        <Link className="brand nano-brand" to="/" data-testid="iris-home-link"><span className="brand-mark">I</span></Link>

        <nav className="sidebar-nav" aria-label="Navigation principale">
          <NavLink end className="nav-link" to="/" data-testid="active-tickets-link" title="Dossiers actifs"><Grid2X2 size={18} /></NavLink>
          <NavLink className="nav-link" to="/archives" data-testid="archives-link" title="Archives"><Archive size={18} /></NavLink>
          <button className="nav-link icon-button" type="button" data-testid="notifications-button" title="Alertes"><Bell size={18} /></button>
          <button className="nav-link icon-button" type="button" data-testid="settings-button" title="Réglages"><Settings2 size={18} /></button>
        </nav>

        <div className="ticket-queue" data-testid="recent-tickets-list">
          <div className="queue-heading"><span>FILE DE TICKETS</span><b>{tickets.length}</b></div>
          <Link className="queue-create" to="/new" data-testid="sidebar-new-ticket-button"><Plus size={15} /> Nouveau dossier</Link>
          {isDemo && <div className="demo-ribbon" data-testid="demo-mode-indicator">MODE DÉMO</div>}
          <div className="queue-scroll">
          {tickets.map((ticket) => (
            <Link
              className="queue-ticket"
              key={ticket.id}
              to={`/tickets/${ticket.id}`}
              data-testid={`recent-ticket-${ticket.id}`}
            >
              <span className="queue-avatar">
                {ticket.member.avatar_url ? (
                  <img alt="" src={ticket.member.avatar_url} />
                ) : (
                  ticket.member.username.slice(0, 1).toUpperCase()
                )}
              </span>
              <span className="queue-ticket-copy">
                <small>{ticket.id}</small>
                <strong>{ticket.member.display_name || ticket.member.username}</strong>
                <em>{ticket.title}</em>
                <i className={`queue-status ${ticket.status}`}>{ticket.status === "active" ? "EN COURS" : "RÉSOLU"}</i>
              </span>
            </Link>
          ))}
          {tickets.length === 0 && <p className="empty-small" data-testid="no-recent-tickets">Aucun dossier en file.</p>}
          </div>
        </div>

        <div className="sidebar-bottom">
          <div className="helper-identity" data-testid="helper-identity">
            <span className="helper-avatar">
              {helper?.avatar_url ? <img src={helper.avatar_url} alt="" /> : <RadioTower size={15} />}
            </span>
            <span>
              <strong>{helper?.global_name || helper?.username}</strong>
              <small>{isDemo ? "Session de démonstration" : "Helper connecté"}</small>
            </span>
            <button
              aria-label="Se déconnecter"
              className="icon-button"
              onClick={onLogout}
              title="Se déconnecter"
              type="button"
              data-testid="logout-button"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}