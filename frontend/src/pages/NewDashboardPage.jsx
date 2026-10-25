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
import "@/NewDashboard.css";

export default function NewDashboardPage({
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

  const pills = [
    isHelper && { label: "Helper", cls: "pill-helper" },
    isStaff && { label: "Staff", cls: "pill-staff" },
    isResponsable && { label: "Responsable", cls: "pill-responsable" },
    isAnimateur && { label: "Animateur", cls: "pill-animateur" },
    isOperateur && { label: "Opérateur", cls: "pill-operateur" },
    isAdmin && { label: "Admin", cls: "pill-admin" },
  ].filter(Boolean);

  const modules = [
    (isHelper || isResponsable || isAdmin) && {
      to: "/new",
      icon: <Plus size={22} />,
      title: "Nouveau suivi",
      desc: "Importer un salon Discord",
    },
    (isHelper || isResponsable || isAdmin) && {
      to: "/archives",
      icon: <HeartHandshake size={22} />,
      title: "Mes suivis",
      desc: `${stats.active_count} ouvert(s) · ${stats.archived_count} archivé(s)`,
    },
    isStaff && {
      to: "/staff/calendrier",
      icon: <CalendarDays size={22} />,
      title: "Calendrier staff",
      desc: "Absences et disponibilités",
    },
    isStaff && {
      to: "/staff/meetings",
      icon: <BookHeart size={22} />,
      title: "Réunions",
      desc: "Comptes-rendus et médias",
    },
    isStaff && {
      to: "/staff/taches",
      icon: <ShieldCheck size={22} />,
      title: "Tâches trimestrielles",
      desc: "Périodes et volontaires",
    },
    (isAnimateur || isResponsable) && {
      to: "/animateur/projects",
      icon: <FolderKanban size={22} />,
      title: "Projets animateur",
      desc: "Projets, tâches et ressources",
    },
    isOperateur && {
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
    <section className="nd-page" data-testid="new-dashboard-page">
      <header className="nd-welcome">
        <h1>Bienvenue {pseudo}</h1>
        <div className="nd-pills">
          {pills.map((p) => (
            <span key={p.label} className={`nd-pill ${p.cls}`}>
              {p.label}
            </span>
          ))}
        </div>
      </header>

      <div className="nd-grid">
        {modules.map((m) => (
          <Link key={m.to} to={m.to} className="nd-card">
            <div className="nd-icon">{m.icon}</div>
            <div className="nd-text">
              <strong>{m.title}</strong>
              <span>{m.desc}</span>
            </div>
            <ArrowRight size={18} className="nd-arrow" />
          </Link>
        ))}
      </div>

      {(isHelper || isResponsable || isAdmin) && (
        <section className="nd-recent">
          <h2>Dernier suivi</h2>
          {latest ? (
            <Link to={`/tickets/${latest.id}`} className="nd-recent-card">
              <span>{latest.title}</span>
              <ArrowRight size={16} />
            </Link>
          ) : (
            <p className="nd-empty">Aucun suivi pour le moment.</p>
          )}
        </section>
      )}
    </section>
  );
}
