import { Archive, Grid2X2, LogOut, RadioTower } from "lucide-react";
import { Link, NavLink } from "react-router-dom";


export default function AppShell({ children, helper, tickets, onLogout }) {
  return (
    <div className="app-shell" data-testid="iris-application">
      <aside className="sidebar nano-sidebar" data-testid="main-navigation">
        <Link className="brand nano-brand" to="/" data-testid="iris-home-link"><span className="brand-mark">I</span></Link>

        <nav className="sidebar-nav" aria-label="Navigation principale">
          <NavLink end className="nav-link" to="/" data-testid="active-tickets-link" title="Dossiers actifs"><Grid2X2 size={18} /></NavLink>
          <NavLink className="nav-link" to="/archives" data-testid="archives-link" title="Archives"><Archive size={18} /></NavLink>
        </nav>

        <div className="sidebar-bottom">
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