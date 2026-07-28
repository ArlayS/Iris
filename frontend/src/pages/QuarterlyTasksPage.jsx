import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Calendar, Plus, Trash2, UserCheck, UserPlus } from "lucide-react";
import { api, getErrorMessage } from "../api/client";

function formatDate(value) {
  return new Date(value).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

export default function QuarterlyTasksPage({ isResponsable, helper }) {
  const [period, setPeriod] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [periodStart, setPeriodStart] = useState(() => new Date().toISOString().slice(0, 10));
  const [creatingPeriod, setCreatingPeriod] = useState(false);

  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [explanation, setExplanation] = useState("");
  const [taskDate, setTaskDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const periodResponse = await api.get("/staff/tasks/period");
      setPeriod(periodResponse.data);
      if (periodResponse.data) {
        const tasksResponse = await api.get("/staff/tasks", { params: { period_id: periodResponse.data.id } });
        setTasks(tasksResponse.data);
      } else {
        setTasks([]);
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const declarePeriod = async (event) => {
    event.preventDefault();
    setCreatingPeriod(true);
    try {
      const response = await api.post("/staff/tasks/period", { start_date: periodStart });
      setPeriod(response.data);
      setTasks([]);
      toast.success("Période déclarée.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setCreatingPeriod(false);
    }
  };

  const addTask = async (event) => {
    event.preventDefault();
    if (!name.trim() || !category.trim() || !taskDate) return;
    setSubmitting(true);
    try {
      const response = await api.post("/staff/tasks", {
        period_id: period.id,
        name,
        category,
        explanation,
        task_date: taskDate,
      });
      setTasks((current) => [...current, response.data]);
      setName("");
      setCategory("");
      setExplanation("");
      toast.success("Tâche ajoutée.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  const removeTask = async (taskId) => {
    try {
      await api.delete(`/staff/tasks/${taskId}`);
      setTasks((current) => current.filter((task) => task.id !== taskId));
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const toggleSignup = async (task) => {
    try {
      const response = await api.post(`/staff/tasks/${task.id}/signup`);
      setTasks((current) => current.map((item) => (item.id === task.id ? response.data : item)));
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const isSignedUp = (task) => helper && task.volunteers.some((v) => v.id === helper.id);

  return (
    <section className="page-content dashboard-page" data-testid="quarterly-tasks-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>Tâches trimestrielles</h1>
        </div>
      </header>

      {loading ? (
        <p className="dashboard-loading">Chargement…</p>
      ) : (
        <>
          {period ? (
            <div className="lock-banner" style={{ background: "#e8efea", color: "#365443" }}>
              <Calendar size={14} /> Période en cours : {formatDate(period.start_date)} → {formatDate(period.end_date)}
            </div>
          ) : (
            <p className="dashboard-empty">Aucune période déclarée pour l'instant.</p>
          )}

          {isResponsable && (
            <form onSubmit={declarePeriod} className="meeting-inline-form" style={{ marginTop: "16px", marginBottom: "24px" }}>
              <div className="meeting-inline-form-header">
                <span>Déclarer une nouvelle période (3 mois)</span>
              </div>
              <input
                type="date"
                className="meeting-inline-input"
                value={periodStart}
                onChange={(e) => setPeriodStart(e.target.value)}
              />
              <button type="submit" className="meeting-inline-submit" disabled={creatingPeriod}>
                {creatingPeriod ? "Enregistrement…" : "Déclarer la période"}
              </button>
            </form>
          )}

          {period && isResponsable && (
            <form onSubmit={addTask} className="meeting-inline-form" style={{ marginBottom: "24px" }}>
              <div className="meeting-inline-form-header">
                <span>Ajouter une tâche</span>
              </div>
              <input
                className="meeting-inline-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Nom de la tâche"
                maxLength={160}
              />
              <input
                className="meeting-inline-input"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="Catégorie (ex: Communication, Support…)"
                maxLength={80}
              />
              <textarea
                className="meeting-inline-textarea"
                value={explanation}
                onChange={(e) => setExplanation(e.target.value)}
                placeholder="Explication détaillée de la tâche…"
                rows={3}
              />
              <input
                type="date"
                className="meeting-inline-input"
                value={taskDate}
                onChange={(e) => setTaskDate(e.target.value)}
              />
              <button type="submit" className="meeting-inline-submit" disabled={submitting}>
                <Plus size={16} /> {submitting ? "Enregistrement…" : "Ajouter la tâche"}
              </button>
            </form>
          )}

          <div className="meetings-list-card dashboard-card">
            {tasks.length === 0 ? (
              <p className="dashboard-empty">Aucune tâche pour cette période.</p>
            ) : (
              <div className="meeting-list">
                {tasks.map((task) => (
                  <div key={task.id} className="meeting-row" style={{ flexDirection: "column", alignItems: "stretch", gap: "10px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px" }}>
                      <div>
                        <span className="category-badge">{task.category}</span>
                        <div style={{ fontWeight: 600, fontSize: "15px", marginTop: "6px" }}>{task.name}</div>
                        <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "2px" }}>
                          <Calendar size={12} style={{ verticalAlign: "middle", marginRight: "4px" }} />
                          {formatDate(task.task_date)}
                        </div>
                      </div>
                      {isResponsable && (
                        <button type="button" className="icon-btn-danger" onClick={() => removeTask(task.id)} aria-label="Supprimer">
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>

                    {task.explanation && (
                      <p style={{ fontSize: "13px", color: "var(--muted)", margin: 0, lineHeight: 1.5 }}>{task.explanation}</p>
                    )}

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "6px" }}>
                      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                        {task.volunteers.length === 0 ? (
                          <span style={{ fontSize: "12px", color: "var(--muted)" }}>Personne inscrit pour l'instant.</span>
                        ) : (
                          task.volunteers.map((v) => (
                            <span key={v.id} className="status-badge status-done">
                              {v.display_name || v.username}
                            </span>
                          ))
                        )}
                      </div>
                      <button
                        type="button"
                        className={`btn-ghost ${isSignedUp(task) ? "is-secondary" : ""}`}
                        onClick={() => toggleSignup(task)}
                      >
                        {isSignedUp(task) ? <UserCheck size={16} /> : <UserPlus size={16} />}
                        {isSignedUp(task) ? "Inscrit" : "S'inscrire"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
