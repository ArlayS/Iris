import { Archive, CircleHelp, FolderKanban, LogOut, Plus, RadioTower } from "lucide-react";
import { Link, NavLink } from "react-router-dom";


export default function AppShell({ children, helper, tickets, onLogout }) {
  return (
    <div className="app-shell" data-testid="iris-application">
      <aside className="sidebar" data-testid="main-navigation">
        <Link className="brand" to="/" data-testid="iris-home-link">
          <span className="brand-mark">I</span>
          <span>
            <strong>IRIS</strong>
            <small>HELPER SYSTEM</small>
          </span>
        </Link>

        <nav className="sidebar-nav" aria-label="Navigation principale">
          <NavLink end className="nav-link" to="/" data-testid="active-tickets-link">
            <FolderKanban size={16} />
            <span>Tickets actifs</span>
            <b>{tickets.filter((ticket) => ticket.status === "active").length}</b>
          </NavLink>
          <NavLink className="nav-link" to="/archives" data-testid="archives-link">
            <Archive size={16} />
            <span>Archives</span>
          </NavLink>
          <a
            className="nav-link"
            href="https://discord.com/developers/applications"
            target="_blank"
            rel="noreferrer"
            data-testid="discord-portal-link"
          >
            <CircleHelp size={16} />
            <span>Console Discord</span>
          </a>
        </nav>

        <div className="sidebar-ticket-list" data-testid="recent-tickets-list">
          <p className="eyebrow">RÉCENTS</p>
          {tickets.slice(0, 7).map((ticket) => (
            <Link
              className="compact-ticket"
              key={ticket.id}
              to={`/tickets/${ticket.id}`}
              data-testid={`recent-ticket-${ticket.id}`}
            >
              <span className="compact-ticket-avatar">
                {ticket.member.avatar_url ? (
                  <img alt="" src={ticket.member.avatar_url} />
                ) : (
                  ticket.member.username.slice(0, 1).toUpperCase()
                )}
              </span>
              <span>
                <strong>{ticket.member.display_name || ticket.member.username}</strong>
                <small>#{ticket.channel_name}</small>
              </span>
            </Link>
          ))}
          {tickets.length === 0 && <p className="empty-small" data-testid="no-recent-tickets">Aucun ticket synchronisé.</p>}
        </div>

        <div className="sidebar-bottom">
          <Link className="new-ticket-side" to="/new" data-testid="sidebar-new-ticket-button">
            <Plus size={16} /> Nouveau ticket
          </Link>
          <div className="helper-identity" data-testid="helper-identity">
            <span className="helper-avatar">
              {helper?.avatar_url ? <img src={helper.avatar_url} alt="" /> : <RadioTower size={15} />}
            </span>
            <span>
              <strong>{helper?.global_name || helper?.username}</strong>
              <small>Helper connecté</small>
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