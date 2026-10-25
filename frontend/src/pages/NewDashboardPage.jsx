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
  Radio,
  Archive,
} from "lucide-react";
import { Link } from "react-router-dom";
import "@/NewDashboard.css";
import { useEffect } from "react";

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
  const pseudo = helper?.display_name || helper?.username || "toi";
  const myTickets = tickets.filter(
    (t) => t.assigned_helper?.id === helper?.id
  );
useEffect(() => {
  document.body.classList.add("dashboard-no-nav");
  return () => document.body.classList.remove("dashboard-no-nav");
}, []);
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
      icon: <Plus size={20} />,
      title: "Nouveau suivi",
      desc: "Importer un salon Discord",
    },
    (isHelper || isResponsable || isAdmin) && {
      to: "/archives",
      icon: <HeartHandshake size={20} />,
      title: "Mes suivis",
      desc: `${stats.active_count} ouvert(s)`,
    },
    isStaff && {
      to: "/staff/calendrier",
      icon: <CalendarDays size={20} />,
      title: "Calendrier staff",
      desc: "Absences",
    },
    isStaff && {
      to: "/staff/meetings",
      icon: <FileText size={20} />,
      title: "Réunions",
      desc: "Comptes-rendus",
    },
    isStaff && {
      to: "/staff/taches",
      icon: <ShieldCheck size={20} />,
      title: "Tâches",
      desc: "Trimestrielles",
    },
    (isAnimateur || isResponsable) && {
      to: "/animateur/projects",
      icon: <FolderKanban size={20} />,
      title: "Projets",
      desc: "Animateur",
    },
    isOperateur && {
      to: "/moderation/casiers",
      icon: <Users size={20} />,
      title: "Casiers",
      desc: "Modération",
    },
    isResponsable && {
      to: "/responsable/auth-logs",
      icon: <Archive size={20} />,
      title: "Logs",
      desc: "Authentification",
    },
    isAdmin && {
      to: "/admin",
      icon: <ShieldCheck size={20} />,
      title: "Admin",
      desc: "Helpers",
    },
  ].filter(Boolean);

  return (
    <section className="page-content dashboard-page" data-testid="new-dashboard-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE IRIS</p>
          <h1>Bienvenue {pseudo}</h1>
        </div>
        <div className="nd-pills">
          {pills.map((p) => (
            <span key={p.label} className={`nd-pill ${p.cls}`}>
              {p.label}
            </span>
          ))}
        </div>
      </header>

      <div className="metrics-grid">
        <div className="metric-block"><HeartHandshake size={18} /><span>Suivis ouverts</span><strong>{stats.active_count}</strong></div>
        <div className="metric-block"><BookHeart size={18} /><span>Échanges</span><strong>{stats.total_messages}</strong></div>
        <div className="metric-block"><ShieldCheck size={18} /><span>Stabilisés</span><strong>{stats.archived_count}</strong></div>
      </div>

      <div className="dashboard-grid">
        <section className="activity-pane">
          <div className="section-heading"><span>MES DERNIERS SUIVIS</span><span className="live-dot">INTERLOCUTEUR</span></div>
          {isHelper ? (
            myTickets.length === 0 ? (
              <div className="dashboard-empty">
                <Radio size={26} />
                <p>Aucun suivi où vous êtes l’interlocuteur.</p>
              </div>
            ) : (
              <div className="ticket-table">
                {myTickets.slice(0, 5).map((t) => (
                  <Link to={`/tickets/${t.id}`} className="ticket-table-row" key={t.id}>
                    <span className="ticket-table-person">
                      {t.member.avatar_url && <img src={t.member.avatar_url} alt="" />}
                      <strong>{t.member.display_name || t.member.username}</strong>
                    </span>
                    <span>{t.message_count} échanges</span>
                    <span className={`status-dot ${t.status}`}>
                      {t.status === "active" ? "ACTIF" : "ARCHIVÉ"}
                    </span>
                  </Link>
                ))}
              </div>
            )
          ) : (
            <p className="dashboard-empty">Section réservée aux helpers.</p>
          )}
        </section>

        <aside className="system-pane">
          <p className="eyebrow">ACCÈS RAPIDES</p>
          <div className="nd-modules">
            {modules.map((m) => (
              <Link key={m.to} to={m.to} className="nd-module">
                {m.icon}
                <span>{m.title}</span>
                <ArrowRight size={14} />
              </Link>
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}
