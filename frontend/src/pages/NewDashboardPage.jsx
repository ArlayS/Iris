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
import HelperDashboardModule from "../components/HelperDashboardModule";
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
{isResponsable && (
  <section
    className="nd-responsable-banner"
    aria-labelledby="nd-responsable-title"
  >
    <div className="nd-responsable-content">
      <p className="nd-responsable-eyebrow">ESPACE RESPONSABLE</p>

      <h2 id="nd-responsable-title">
        Veiller au bon fonctionnement d’Iris.
      </h2>

      <p className="nd-responsable-description">
        Consultez les journaux d’accès et retrouvez les sauvegardes
        des salons Discord.
      </p>
    </div>

    <nav
      className="nd-responsable-actions"
      aria-label="Outils du responsable"
    >
      <Link
        to="/responsable/auth-logs"
        className="nd-responsable-link"
      >
        <FileText size={18} aria-hidden="true" />
        <span>Logs d’authentification</span>
        <ArrowRight size={18} aria-hidden="true" />
      </Link>

      <Link
        to="/responsable/archives-salons"
        className="nd-responsable-link"
      >
        <Archive size={18} aria-hidden="true" />
        <span>Sauvegardes de salons</span>
        <ArrowRight size={18} aria-hidden="true" />
      </Link>
    </nav>
  </section>
)}
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

      {(isHelper || isAdmin) && (
  <HelperDashboardModule
    tickets={tickets}
    helper={helper}
    isAdmin={isAdmin}
  />
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
