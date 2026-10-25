import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  FolderKanban,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/client";

function formatDate(value) {
  if (!value) return "Sans échéance";

  const date = new Date(
    /^\d{4}-\d{2}-\d{2}$/.test(value)
      ? `${value}T12:00:00`
      : value
  );

  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "long",
  });
}

function ProjectPreview({ project, helperId }) {
  const tasksQuery = useQuery({
    queryKey: ["dashboard", "project-tasks", project.id, helperId],
    queryFn: async ({ signal }) => {
      const response = await api.get(
        `/animateur/projects/${project.id}/tasks`,
        { signal }
      );

      if (!Array.isArray(response.data)) {
        throw new Error("Format des tâches de projet inattendu.");
      }

      return response.data
        .filter(
          (task) =>
            String(task.assignee?.id) === String(helperId) &&
            task.status === "a_faire"
        )
        .sort((a, b) =>
          (a.due_date || "9999").localeCompare(b.due_date || "9999")
        );
    },
    staleTime: 30_000,
    refetchOnWindowFocus: true,
    retry: false,
  });

  return (
    <article className="nd-project-preview">
      <header className="nd-project-preview-header">
        <span className="nd-project-preview-icon">
          <FolderKanban size={22} aria-hidden="true" />
        </span>

        <div>
          <h3>{project.title}</h3>
          <p>
            <CalendarDays size={14} aria-hidden="true" />
            {project.end_date
              ? `Fin prévue : ${formatDate(project.end_date)}`
              : "Projet en cours"}
          </p>
        </div>

        <Link
          to={`/animateur/projects/${project.id}`}
          className="nd-project-open"
          aria-label={`Ouvrir le projet ${project.title}`}
        >
          <ArrowRight size={19} aria-hidden="true" />
        </Link>
      </header>

      {project.description && (
        <p className="nd-project-description">
          {project.description}
        </p>
      )}

      <div className="nd-project-tasks">
        <p className="nd-project-tasks-label">
          MES TÂCHES À RÉALISER
        </p>

        {tasksQuery.isPending ? (
          <p className="nd-project-note" role="status">
            Chargement des tâches…
          </p>
        ) : tasksQuery.isError ? (
          <div className="nd-project-note" role="alert">
            <p>Impossible de charger les tâches de ce projet.</p>
            <button type="button" onClick={() => tasksQuery.refetch()}>
              Réessayer
            </button>
          </div>
        ) : tasksQuery.data.length === 0 ? (
          <p className="nd-project-note">
            <CheckCircle2 size={17} aria-hidden="true" />
            Aucune tâche à réaliser ne vous est attribuée.
          </p>
        ) : (
          tasksQuery.data.map((task) => (
            <Link
              key={task.id}
              to={`/animateur/projects/${project.id}`}
              className="nd-project-task"
            >
              <span>
                <strong>{task.title}</strong>
                <small>{formatDate(task.due_date)}</small>
              </span>
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          ))
        )}
      </div>

      <Link
        to={`/animateur/projects/${project.id}`}
        className="nd-project-footer"
      >
        Consulter le projet et rendre mon travail
        <ArrowRight size={16} aria-hidden="true" />
      </Link>
    </article>
  );
}

export default function AnimateurDashboardModule({ helper }) {
  const projectsQuery = useQuery({
    queryKey: ["dashboard", "my-projects", helper?.id],
    enabled: Boolean(helper?.id),
    queryFn: async ({ signal }) => {
      const response = await api.get("/animateur/projects", {
        signal,
      });

      if (!Array.isArray(response.data)) {
        throw new Error("Format des projets inattendu.");
      }

      return response.data.filter(
        (project) =>
          project.status === "en_cours" &&
          (project.members || []).some(
            (member) => String(member.id) === String(helper.id)
          )
      );
    },
    staleTime: 30_000,
    refetchOnWindowFocus: true,
    retry: false,
  });

  return (
    <section className="nd-work-module nd-work-module--animateur">
      <header className="nd-work-header">
        <div>
          <p className="nd-eyebrow">CRÉER ENSEMBLE</p>
          <h2>Mon espace animateur</h2>
          <p className="nd-description">
            Vos projets en cours et les prochaines tâches qui vous attendent.
          </p>
        </div>

        <Link to="/animateur/projects" className="nd-work-link">
          Tous les projets
          <ArrowRight size={17} aria-hidden="true" />
        </Link>
      </header>

      {projectsQuery.isPending ? (
        <div className="nd-work-panel nd-work-message" role="status">
          Chargement de vos projets…
        </div>
      ) : projectsQuery.isError ? (
        <div className="nd-work-panel nd-work-message" role="alert">
          <p>Impossible de charger vos projets.</p>
          <button type="button" onClick={() => projectsQuery.refetch()}>
            Réessayer
          </button>
        </div>
      ) : projectsQuery.data.length === 0 ? (
        <div className="nd-work-panel nd-work-message">
          Vous ne participez à aucun projet en cours pour le moment.
        </div>
      ) : (
        <div className="nd-project-grid">
          {projectsQuery.data.map((project) => (
            <ProjectPreview
              key={project.id}
              project={project}
              helperId={helper.id}
            />
          ))}
        </div>
      )}
    </section>
  );
}
