import { Archive, BookOpenText, Grid2X2, LayoutDashboard, LogOut, RadioTower, UserRound } from "lucide-react";
import { Link, NavLink } from "react-router-dom";


export default function AppShell({ children, helper, tickets, onLogout, isAdmin }) {
  return (
    <div className="app-shell" data-testid="iris-application">
      <aside className="sidebar nano-sidebar" data-testid="main-navigation">
        <Link className="brand nano-brand" to="/" data-testid="iris-home-link"><img src="https://customer-assets-lqy194kg.emergentagent.net/job_iris-logs/artifacts/jhsbq3v9_image.png" alt="Iris" data-testid="iris-logo" /></Link>

        <nav className="sidebar-nav" aria-label="Navigation principale">
          <NavLink end className="nav-link" to="/" data-testid="active-tickets-link" title="Dossiers actifs"><Grid2X2 size={18} /><span>Suivis</span></NavLink>
          <NavLink className="nav-link" to="/archives" data-testid="archives-link" title="Archives"><Archive size={18} /><span>Archives</span></NavLink>
          <NavLink className="nav-link" to="/resources" data-testid="sidebar-resources-link" title="Ressources"><BookOpenText size={18} /><span>Ressources</span></NavLink>
          <NavLink className="nav-link" to="/profile" data-testid="helper-profile-link" title="Mon profil"><UserRound size={18} /><span>Mon profil</span></NavLink>
          <NavLink className="nav-link" to="/admin" data-testid="admin-panel-link" title="Vue administrateur"><LayoutDashboard size={18} /><span>Administration</span></NavLink>
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