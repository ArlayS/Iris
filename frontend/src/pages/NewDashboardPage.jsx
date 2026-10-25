import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Archive,
  BookHeart,
  CalendarDays,
  CheckCircle2,
  FileText,
  FolderKanban,
  HeartHandshake,
  Plus,
  Radio,
  ShieldCheck,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import "@/NewDashboard.css";

function localDateKey() {
  const now = new Date();

  return [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
}

function timestamp(value) {
  const result = Date.parse(value || "");
  return Number.isNaN(result) ? 0 : result;
}

export default function NewDashboardPage({
  stats = {},
  tickets = [],
  helper,
  isAdmin = false,
  isStaff = false,
  isHelper = false,
  isResponsable = false,
  isOperateur = false,
  isAnimateur = false,
}) {
  useEffect(() => {
    document.body.classList.add("dashboard-no-nav");

    return () => {
      document.body.classList.remove("dashboard-no-nav");
    };
  }, []);

  const pseudo =
    helper?.global_name ||
    helper?.display_name ||
    helper?.username ||
    "toi";

  const canSeeModeration = isOperateur || isResponsable;
  const canSeeStaff =
    isStaff || isResponsable || isAdmin || isHelper || isOperateur;

  const absencesQuery = useQuery({
    queryKey: ["dashboard", "absences", helper?.id],
    queryFn: async ({ signal }) => {
      const response = await api.get("/staff/calendrier", { signal });

      if (!Array.isArray(response.data)) {
        throw new Error("Format de réponse inattendu pour les absences.");
      }

      return response.data;
    },
    enabled: Boolean(helper?.id && canSeeStaff),
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    retry: false,
  });

  const today = localDateKey();

  const currentAbsence = absencesQuery.data?.find(
    (absence) =>
      String(absence.helper?.id) === String(helper?.id) &&
      absence.start_date <= today &&
      absence.end_date >= today
  );

  let presenceLabel = "Statut indisponible";
  let presenceState = "unknown";

  if (canSeeStaff && absencesQuery.isPending) {
    presenceLabel = "Vérification du statut…";
  } else if (canSeeStaff && !absencesQuery.isError) {
    presenceLabel = currentAbsence ? "En absence" : "Aucune absence déclarée";
    presenceState = currentAbsence ? "away" : "available";
  }

  const myTickets = helper?.id
    ? tickets
        .filter(
          (ticket) =>
            String(ticket.assigned_helper?.id) === String(helper.id)
        )
        .sort(
          (a, b) =>
            timestamp(b.updated_at || b.created_at) -
            timestamp(a.updated_at || a.created_at)
        )
        .slice(0, 5)
    : [];

  const pills = [
    isHelper && { label: "Helper", tone: "helper" },
    isStaff && { label: "Staff", tone: "staff" },
    isResponsable && { label: "Responsable", tone: "responsable" },
    isAnimateur && { label: "Animateur", tone: "animateur" },
    isOperateur && { label: "Opérateur", tone: "operateur" },
    isAdmin && { label: "Coordinateur", tone: "admin" },
  ].filter(Boolean);

  const quickCards = [
    canSeeModeration && {
      to: "/moderation/casiers",
      title: "Accéder au casier",
      description: "Consulter les dossiers et les historiques de modération.",
      tone: "red",
      Icon: ShieldCheck,
    },
    canSeeStaff && {
      to: "/staff/meetings",
      title: "Voir les réunions passées",
      description: "Retrouver les comptes-rendus et les documents partagés.",
      tone: "blue",
      Icon: FileText,
    },
    canSeeStaff && {
      to: "/staff/calendrier",
      title: "Calendrier",
      description: "Consulter les absences et déclarer une indisponibilité.",
      tone: "white",
      Icon: CalendarDays,
    },
  ].filter(Boolean);

  const extraLinks = [
    canSeeStaff && {
      to: "/staff/taches",
      label: "Tâches trimestrielles",
      Icon: CheckCircle2,
    },
    (isAnimateur || isResponsable) && {
      to: "/animateur/projects",
      label: "Projets animateur",
      Icon: FolderKanban,
    },
    (isAnimateur || isResponsable) && {
      to: "/animateur/calendrier",
      label: "Calendrier des projets",
      Icon: CalendarDays,
    },
    isHelper && {
      to: "/resources",
      label: "Ressources",
      Icon: BookHeart,
    },
    isResponsable && {
      to: "/responsable/auth-logs",
      label: "Logs d’authentification",
      Icon: Archive,
    },
    isResponsable && {
      to: "/responsable/archives-salons",
      label: "Archives de salons",
      Icon: Archive,
    },
    (isAdmin || isResponsable) && {
      to: "/admin",
      label: "Coordination",
      Icon: Users,
    },
    {
      to: "/profile",
      label: "Mon profil",
      Icon: Users,
    },
  ].filter(Boolean);

  return (
    <section className="nd-page" data-testid="new-dashboard-page">
      <header className="nd-header">
        <div className="nd-heading">
          <p className="nd-eyebrow">ESPACE IRIS</p>

          <h1>Bienvenue {pseudo}</h1>

          <div className="nd-pills" aria-label="Vos accès">
            {pills.map((pill) => (
              <span
                key={pill.label}
                className={`nd-pill nd-pill--${pill.tone}`}
              >
                {pill.label}
              </span>
            ))}
          </div>
        </div>

        {canSeeStaff ? (
          <Link
            to="/staff/calendrier"
            className={`nd-presence nd-presence--${presenceState}`}
            title="Ouvrir le calendrier des absences"
          >
            <span className="nd-presence-dot" aria-hidden="true" />
            <span aria-live="polite">{presenceLabel}</span>
            <CalendarDays size={17} aria-hidden="true" />
          </Link>
        ) : (
          <span className="nd-presence nd-presence--unknown">
            Statut d’absence non accessible
          </span>
        )}
      </header>

      {quickCards.length > 0 && (
        <nav className="nd-shortcuts" aria-label="Accès principaux">
          {quickCards.map(({ to, title, description, tone, Icon }) => (
            <Link
              key={to}
              to={to}
              className={`nd-shortcut nd-shortcut--${tone}`}
            >
              <span className="nd-shortcut-icon">
                <Icon size={23} aria-hidden="true" />
              </span>

              <h2>{title}</h2>
              <p>{description}</p>

              <span className="nd-shortcut-footer">
                Ouvrir
                <ArrowRight size={18} aria-hidden="true" />
              </span>
            </Link>
          ))}
        </nav>
      )}

      {isHelper && (
        <section className="nd-helper" aria-labelledby="nd-helper-title">
          <div className="nd-section-heading">
            <div>
              <p className="nd-eyebrow">ACCOMPAGNEMENT</p>
              <h2 id="nd-helper-title">Mon espace helper</h2>
              <p className="nd-description">
                Vos repères et les derniers suivis dont vous êtes
                l’interlocuteur.
              </p>
            </div>

            <Link className="nd-button" to="/new">
              <Plus size={17} aria-hidden="true" />
              Nouveau suivi
            </Link>
          </div>

          <div className="nd-metrics">
            <div className="nd-metric">
              <span>
                <HeartHandshake size={17} aria-hidden="true" />
                Suivis ouverts
              </span>
              <strong>{stats.active_count ?? 0}</strong>
            </div>

            <div className="nd-metric">
              <span>
                <BookHeart size={17} aria-hidden="true" />
                Échanges consignés
              </span>
              <strong>{stats.total_messages ?? 0}</strong>
            </div>

            <div className="nd-metric">
              <span>
                <ShieldCheck size={17} aria-hidden="true" />
                Suivis archivés
              </span>
              <strong>{stats.archived_count ?? 0}</strong>
            </div>
          </div>

          <div className="nd-tickets">
            <div className="nd-tickets-heading">
              <h3>Mes derniers suivis</h3>
              <span>Interlocuteur attribué</span>
            </div>

            {myTickets.length > 0 ? (
              <div className="nd-ticket-list">
                {myTickets.map((ticket) => {
                  const member = ticket.member || {};
                  const name =
                    member.display_name ||
                    member.username ||
                    ticket.title ||
                    "Membre";

                  return (
                    <Link
                      key={ticket.id}
                      to={`/tickets/${ticket.id}`}
                      className="nd-ticket"
                    >
                      <span className="nd-ticket-person">
                        <span className="nd-avatar">
                          {member.avatar_url ? (
                            <img
                              src={member.avatar_url}
                              alt=""
                              loading="lazy"
                            />
                          ) : (
                            <Users size={17} aria-hidden="true" />
                          )}
                        </span>

                        <span className="nd-ticket-copy">
                          <strong>{name}</strong>
                          <small>{ticket.title || "Ticket d’aide"}</small>
                        </span>
                      </span>

                      <span className="nd-ticket-count">
                        {ticket.message_count ?? 0} échanges
                      </span>

                      <span
                        className={`nd-ticket-status ${
                          ticket.status === "active"
                            ? "nd-ticket-status--active"
                            : ""
                        }`}
                      >
                        {ticket.status === "active" ? "Actif" : "Archivé"}
                      </span>

                      <ArrowRight size={17} aria-hidden="true" />
                    </Link>
                  );
                })}
              </div>
            ) : (
              <div className="nd-empty">
                <Radio size={27} aria-hidden="true" />
                <p>Aucun suivi ne vous est attribué pour le moment.</p>
              </div>
            )}
          </div>
        </section>
      )}

      <section className="nd-other" aria-labelledby="nd-other-title">
        <h2 id="nd-other-title">Mes autres accès</h2>

        <nav className="nd-other-links" aria-label="Autres espaces">
          {extraLinks.map(({ to, label, Icon }) => (
            <Link key={to} to={to} className="nd-other-link">
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          ))}
        </nav>
      </section>
    </section>
  );
}
