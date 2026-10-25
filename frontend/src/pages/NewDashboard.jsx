import {
  ArrowRight,
  BookHeart,
  CalendarDays,
  FolderKanban,
  HeartHandshake,
  Plus,
  ShieldCheck,
  Users,
  FileText,
  Archive,
} from "lucide-react";
import { Link } from "react-router-dom";

export default function DashboardPage({
  stats,
  tickets,
  helper,
  isAdmin,
  isStaff,
  isHelper,
  isResponsable,
  isOperateur,
  isAnimateur,
}) {
  const latest = tickets[0];
  const pseudo = helper?.display_name || helper?.username || "toi";

  const accessPills = [
    isHelper && { label: "Helper", color: "pill-helper" },
    isStaff && { label: "Staff", color: "pill-staff" },
    isResponsable && { label: "Responsable", color: "pill-responsable" },
    isAnimateur && { label: "Animateur", color: "pill-animateur" },
    isOperateur && { label: "Opérateur", color: "pill-operateur" },
    isAdmin && { label: "Admin", color: "pill-admin" },
  ].filter(Boolean);

  const modules = [
    canSeeHelper(isHelper, isResponsable, isAdmin) && {
      to: "/new",
      icon: <Plus size={22} />,
      title: "Nouveau suivi",
      desc: "Importer un salon Discord",
    },
    canSeeHelper(isHelper, isResponsable, isAdmin) && {
      to: "/tickets",
      icon: <HeartHandshake size={22} />,
      title: "Mes suivis",
      desc: `${stats.active_count} suivi(s) ouvert(s)`,
    },
    canSeeStaff && {
      to: "/staff/calendrier",
      icon: <CalendarDays size={22} />,
      title: "Calendrier staff",
      desc: "Absences et disponibilités",
    },
    canSeeStaff && {
      to: "/staff/meetings",
      icon: <FileText size={22} />,
      title: "Réunions",
      desc: "Comptes-rendus et médias",
    },
    canSeeStaff && {
      to: "/staff/taches",
      icon: <ShieldCheck size={22} />,
      title: "Tâches trimestrielles",
      desc: "Périodes et volontaires",
    },
    canSeeAnimateur(isAnimateur, isResponsable) && {
      to: "/animateur/projects",
      icon: <FolderKanban size={22} />,
      title: "Projets animateur",
      desc: "Projets, tâches et ressources",
    },
    canSeeOperateur && {
      to: "/moderation/casiers",
      icon: <Users size={22} />,
      title: "Casiers de modération",
      desc: "Sanctions et historiques",
    },
    isResponsable && {
      to: "/responsable/auth-logs",
      icon: <Archive size={22} />,
      title: "Logs d'authentification",
      desc: "Connexions et accès",
    },
    isResponsable && {
      to: "/responsable/archives-salons",
      icon: <BookHeart size={22} />,
      title: "Archives de salons",
      desc: "Historiques Discord",
    },
    isAdmin && {
      to: "/admin",
      icon: <ShieldCheck size={22} />,
      title: "Administration",
      desc: "Gestion des helpers",
    },
    isAdmin && {
      to: "/resources",
      icon: <BookHeart size={22} />,
      title: "Ressources",
      desc: "Documents partagés",
    },
  ].filter(Boolean);

  return (
    <section className="page-content dashboard-page" data-testid="dashboard-page">
      <header className="dashboard-welcome">
        <h1>Bienvenue {pseudo}</h1>
        <div className="access-pills">
          {accessPills.map((pill) => (
            <span key={pill.label} className={`access-pill ${pill.color}`}>
              {pill.label}
            </span>
          ))}
        </div>
      </header>

      <div className="module-grid">
        {modules.map((mod) => (
          <Link key={mod.to} to={mod.to} className="module-card">
            <div className="module-icon">{mod.icon}</div>
            <div className="module-text">
              <strong>{mod.title}</strong>
              <span>{mod.desc}</span>
            </div>
            <ArrowRight size={18} className="module-arrow" />
          </Link>
        ))}
      </div>

      {canSeeHelper(isHelper, isResponsable, isAdmin) && (
        <section className="dashboard-recent">
          <h2>Dernier suivi</h2>
          {latest ? (
            <Link to={`/tickets/${latest.id}`} className="recent-ticket">
              <span>{latest.title}</span>
              <ArrowRight size={16} />
            </Link>
          ) : (
            <p>Aucun suivi pour le moment.</p>
          )}
        </section>
      )}
    </section>
  );
}

function canSeeHelper(isHelper, isResponsable, isAdmin) {
  return isHelper || isResponsable || isAdmin;
}

function canSeeAnimateur(isAnimateur, isResponsable) {
  return isAnimateur || isResponsable;
}
