import {
  Archive, BookOpenText, CalendarDays, ChevronDown, FileStack, FolderKanban,
  Grid2X2, LayoutDashboard, LogOut, RadioTower, Users,
} from "lucide-react";
import { useState } from "react";
import { Link, NavLink } from "react-router-dom";

export default function AppShell({ children, helper, tickets, onLogout, isAdmin, isStaff, isAnimateur }) {
  const [isHelperMenuOpen, setIsHelperMenuOpen] = useState(true);
  const [isStaffMenuOpen, setIsStaffMenuOpen] = useState(true);
  const [isAnimateurMenuOpen, setIsAnimateurMenuOpen] = useState(true);

  return (
    <div className="app-shell" data-testid="iris-application">
      <aside className="sidebar nano-sidebar" data-testid="main-navigation">
        <Link className="brand nano-brand" to="/" data-testid="iris-home-link">
          <img src="..." alt="Iris" data-testid="iris-logo" />
        </Link>
        <nav className="sidebar-nav" aria-label="Navigation principale">
          {isStaff && (
            <>
              <button
                className="helper-menu-trigger"
                type="button"
                onClick={() => setIsStaffMenuOpen((current) => !current)}
                aria-expanded={isStaffMenuOpen}
                data-testid="staff-menu-toggle"
              >
                <Users size={18} />
                <span>Staff</span>
                <ChevronDown className={isStaffMenuOpen ? "is-open" : ""} size={16} />
              </button>
              <div className={`helper-menu-links ${isStaffMenuOpen ? "is-open" : ""}`} data-testid="staff-menu-links">
                <NavLink className="nav-link" to="/staff/calendrier" data-testid="staff-absences-link" title="Calendrier">
                  <CalendarDays size={18} /><span>Calendrier</span>
                </NavLink>
                <NavLink className="nav-link" to="/staff/meetings" data-testid="staff-meetings-link" title="Résumés de réunions">
                  <FileStack size={18} /><span>Réunions</span>
                </NavLink>
              </div>
            </>
          )}

          {isAnimateur && (
            <>
              <button
                className="helper-menu-trigger"
                type="button"
                onClick={() => setIsAnimateurMenuOpen((current) => !current)}
                aria-expanded={isAnimateurMenuOpen}
                data-testid="animateur-menu-toggle"
              >
                <FolderKanban size={18} />
                <span>Animateur</span>
                <ChevronDown className={isAnimateurMenuOpen ? "is-open" : ""} size={16} />
              </button>
              <div className={`helper-menu-links ${isAnimateurMenuOpen ? "is-open" : ""}`} data-testid="animateur-menu-links">
                <NavLink className="nav-link" to="/animateur/projects" data-testid="animateur-projects-link" title="Projets">
                  <FolderKanban size={18} /><span>Projets</span>
                </NavLink>
                <NavLink className="nav-link" to="/animateur/calendrier" data-testid="animateur-calendar-link" title="Calendrier des projets">
                  <CalendarDays size={18} /><span>Calendrier</span>
                </NavLink>
              </div>
            </>
          )}

          <div className="helper-menu-links is-open" data-testid="helper-menu-links">
            <NavLink end className="nav-link" to="/" data-testid="active-tickets-link" title="Dossiers actifs">
              <Grid2X2 size={18} /><span>Suivis</span>
            </NavLink>
            <NavLink className="nav-link" to="/archives" data-testid="archives-link" title="Archives">
              <Archive size={18} /><span>Archives</span>
            </NavLink>
            <NavLink className="nav-link" to="/resources" data-testid="sidebar-resources-link" title="Ressources">
              <BookOpenText size={18} /><span>Ressources</span>
            </NavLink>
            <NavLink className="nav-link" to="/admin" data-testid="admin-panel-link" title="Vue administrateur">
              <LayoutDashboard size={18} /><span>Coordination</span>
            </NavLink>
          </div>
        </nav>

        <div className="sidebar-bottom">
          <div className="helper-identity" data-testid="helper-identity">
            <Link className="helper-account-link" to="/profile" data-testid="helper-profile-link" title="Ouvrir mon profil">
              <span className="helper-avatar">
                {helper?.avatarurl ? <img src={helper.avatarurl} alt="" /> : <RadioTower size={15} />}
              </span>
              <span>
                <strong>{helper?.globalname || helper?.username}</strong>
                <small>Helper connecté</small>
              </span>
            </Link>
            <button aria-label="Se déconnecter" className="icon-button" onClick={onLogout} title="Se déconnecter" type="button" data-testid="logout-button">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
