import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { FolderKanban, Plus, Users, X } from "lucide-react";
import { api, getErrorMessage } from "../api/client";

const STATUS_LABELS = { en_cours: "En cours", termine: "Terminé", archive: "Archivé" };

function ProjectCard({ project, helper, onJoin, joiningId }) {
  const isMember = project.members.some((member) => member.id === helper?.id);
  const isJoining = joiningId === project.id;

  const handleJoin = (event) => {
    event.preventDefault();
    event.stopPropagation();
    onJoin(project.id);
  };

  return (
    <Link to={`/animateur/projects/${project.id}`} className="resource-card" style={{ textDecoration: "none" }}>
      <span className="resource-type"><FolderKanban size={18} /></span>
      <span className={`status-badge ${project.status === "termine" ? "status-done" : "status-pending"}`}>
        {STATUS_LABELS[project.status]}
      </span>
      <h2>{project.title}</h2>
      <p>{project.description || "Aucune description."}</p>
      <div className="resource-meta">
        <span><Users size={14} /> {project.members.length} membre{project.members.length > 1 ? "s" : ""}</span>
        <span>{project.start_date} → {project.end_date || "…"}</span>
      </div>
      {!isMember && (
        <button
          type="button"
          className="calm-primary-button is-secondary"
          onClick={handleJoin}
          disabled={isJoining}
          style={{ marginTop: 10 }}
        >
          {isJoining ? "Inscription…" : "S'inscrire"}
        </button>
      )}
    </Link>
  );
}

export default function ProjectsListPage({ helper }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [joiningId, setJoiningId] = useState(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [startDate, setStartDate] = useState(new Date().toISOString().slice(0, 10));
  const [endDate, setEndDate] = useState("");

  const load = () => {
    setLoading(true);
    api
      .get("/animateur/projects")
      .then((response) => setProjects(response.data))
      .catch((error) => toast.error(getErrorMessage(error)))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const resetForm = () => {
    setTitle("");
    setDescription("");
    setStartDate(new Date().toISOString().slice(0, 10));
    setEndDate("");
    setShowForm(false);
  };

  const createProject = async (event) => {
    event.preventDefault();
    if (!title.trim()) {
      toast.error("Ajoutez au moins un titre.");
      return;
    }
    setCreating(true);
    try {
      const response = await api.post("/animateur/projects", {
        title, description, start_date: startDate, end_date: endDate || null,
      });
      setProjects((current) => [response.data, ...current]);
      toast.success("Projet créé.");
      resetForm();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setCreating(false);
    }
  };

  const joinProject = async (projectId) => {
    if (!helper?.id) {
      toast.error("Impossible d'identifier votre profil.");
      return;
    }
    setJoiningId(projectId);
    try {
      const response = await api.post(`/animateur/projects/${projectId}/members`, { member_id: helper.id });
      setProjects((current) => current.map((project) => (project.id === projectId ? response.data : project)));
      toast.success("Vous avez rejoint le projet.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setJoiningId(null);
    }
  };

  return (
    <section className="page-content resources-page" data-testid="projects-list-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE ANIMATEUR</p>
          <h1>Projets.</h1>
        </div>
        <div className="dashboard-actions">
          {!showForm ? (
            <button type="button" className="calm-primary-button" onClick={() => setShowForm(true)} data-testid="new-project-button">
              <Plus size={17} /> Nouveau projet
            </button>
          ) : (
            <button type="button" className="calm-primary-button is-cancel" onClick={resetForm}>
              <X size={17} /> Annuler
            </button>
          )}
        </div>
      </header>

      {showForm && (
        <form onSubmit={createProject} className="meeting-inline-form" style={{ marginBottom: 28 }}>
          <div className="meeting-inline-form-header"><span>Nouveau projet</span></div>
          <input
            className="meeting-inline-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Titre du projet"
            maxLength={160}
          />
          <textarea
            className="meeting-inline-textarea"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description du projet"
            rows={3}
          />
          <div className="case-form-grid">
            <div>
              <label>Date de début</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </div>
            <div>
              <label>Date de fin (optionnel)</label>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </div>
          </div>
          <button type="submit" className="meeting-inline-submit" disabled={creating}>
            <Plus size={16} /> {creating ? "Création…" : "Créer le projet"}
          </button>
        </form>
      )}

      {loading ? (
        <p className="resources-empty">Chargement…</p>
      ) : projects.length === 0 ? (
        <p className="resources-empty">Aucun projet pour l'instant.</p>
      ) : (
        <div className="resource-grid">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} helper={helper} onJoin={joinProject} joiningId={joiningId} />
          ))}
        </div>
      )}
    </section>
  );
}
