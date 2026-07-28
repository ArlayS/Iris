import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Archive, Calendar, ChevronDown, Plus, Trash2, UserCheck, UserPlus } from "lucide-react";
import { api, getErrorMessage } from "../api/client";

function formatDate(value) {
  return new Date(value).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

function TaskCard({ task, isResponsable, onRemove, onToggleSignup, isSignedUp }) {
  return (
    <div className="meeting-row" style={{ flexDirection: "column", alignItems: "stretch", gap: "10px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px" }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <span className="category-badge">{task.category}</span>
          <div style={{ fontWeight: 700, fontSize: "20px", marginTop: "8px", color: "var(--ink)" }}>{task.name}</div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", color: "var(--muted)", marginTop: "4px" }}>
            <Calendar size={14} />
            <span>{formatDate(task.task_date)}</span>
          </div>
        </div>
        {isResponsable && onRemove && (
          <button type="button" className="icon-btn-danger" onClick={() => onRemove(task.id)} aria-label="Supprimer">
            <Trash2 size={16} />
          </button>
        )}
      </div>

      {task.explanation && (
        <p style={{ fontSize: "13px", color: "var(--muted)", margin: 0, lineHeight: 1.6, wordBreak: "break-word", overflowWrap: "anywhere" }}>
          {task.explanation}
        </p>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "6px", flexWrap: "wrap", gap: "10px" }}>
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
       {onToggleSignup && (
  <button
    type="button"
    className={`btn-ghost ${isSignedUp ? "btn-locked" : ""}`}
    onClick={() => onToggleSignup(task)}
  >
    {isSignedUp ? <UserMinus size={16} /> : <UserPlus size={16} />}
    {isSignedUp ? "Se désinscrire" : "S'inscrire"}
  </button>
)}
      </div>
    </div>
  );
}

function ArchivedPeriodRow({ period, isOpen, onToggle, isResponsable, onDelete }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    if (tasks.length > 0) return;
    setLoading(true);
    try {
      const response = await api.get("/staff/tasks", { params: { period_id: period.id } });
      setTasks(response.data);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ borderBottom: "1px solid var(--line)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <button
          type="button"
          onClick={() => {
            onToggle(period.id);
            load();
          }}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flex: 1,
            padding: "16px 24px",
            background: "transparent",
            border: "none",
            cursor: "pointer",
            textAlign: "left",
          }}
        >
          <span style={{ fontWeight: 600, fontSize: "14px", color: "var(--ink)" }}>
            {formatDate(period.start_date)} → {formatDate(period.end_date)}
          </span>
          <ChevronDown size={16} style={{ transform: isOpen ? "rotate(180deg)" : "none", transition: "transform 0.15s ease" }} />
        </button>
        {isResponsable && (
          <button
            type="button"
            className="icon-btn-danger"
            onClick={() => onDelete(period.id)}
            aria-label="Supprimer la période"
            style={{ marginRight: "16px" }}
          >
            <Trash2 size={16} />
          </button>
        )}
      </div>
      {isOpen && (
        <div style={{ padding: "0 24px 20px" }}>
          {loading ? (
            <p className="dashboard-loading">Chargement…</p>
          ) : tasks.length === 0 ? (
            <p className="dashboard-empty">Aucune tâche enregistrée pour cette période.</p>
          ) : (
            <div className="meeting-list" style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {tasks.map((task) => (
                <TaskCard key={task.id} task={task} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


export default function QuarterlyTasksPage({ isResponsable, helper }) {
  const [period, setPeriod] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [archivedPeriods, setArchivedPeriods] = useState([]);
  const [openArchiveId, setOpenArchiveId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [periodStart, setPeriodStart] = useState(() => new Date().toISOString().slice(0, 10));
  const [creatingPeriod, setCreatingPeriod] = useState(false);
  const [archiving, setArchiving] = useState(false);

  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [explanation, setExplanation] = useState("");
  const [taskDate, setTaskDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [periodResponse, archivedResponse] = await Promise.all([
        api.get("/staff/tasks/period"),
        api.get("/staff/tasks/periods/archived"),
      ]);
      setPeriod(periodResponse.data);
      setArchivedPeriods(archivedResponse.data);
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
  
const removePeriod = async (periodId) => {
  try {
    await api.delete(`/staff/tasks/period/${periodId}`);
    setArchivedPeriods((current) => current.filter((p) => p.id !== periodId));
    if (openArchiveId === periodId) setOpenArchiveId(null);
    toast.success("Période supprimée.");
  } catch (error) {
    toast.error(getErrorMessage(error));
  }
};
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

  const archivePeriod = async () => {
    if (!period) return;
    setArchiving(true);
    try {
      await api.post(`/staff/tasks/period/${period.id}/archive`);
      toast.success("Période archivée.");
      await load();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setArchiving(false);
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
        {isResponsable && period && (
          <div className="dashboard-actions">
            <button type="button" className="btn-ghost" onClick={archivePeriod} disabled={archiving}>
              <Archive size={16} /> {archiving ? "Archivage…" : "Archiver la période"}
            </button>
          </div>
        )}
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
              <div className="meeting-list" style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                {tasks.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    isResponsable={isResponsable}
                    onRemove={removeTask}
                    onToggleSignup={toggleSignup}
                    isSignedUp={isSignedUp(task)}
                  />
                ))}
              </div>
            )}
          </div>

          <div style={{ marginTop: "32px" }}>
            <div className="section-heading">
              <span>ARCHIVES DES PÉRIODES</span>
            </div>
            <div className="meetings-list-card dashboard-card" style={{ padding: 0 }}>
              {archivedPeriods.length === 0 ? (
                <p className="dashboard-empty" style={{ padding: "24px" }}>Aucune période archivée.</p>
              ) : (
              archivedPeriods.map((archivedPeriod) => (
  <ArchivedPeriodRow
    key={archivedPeriod.id}
    period={archivedPeriod}
    isOpen={openArchiveId === archivedPeriod.id}
    onToggle={(id) => setOpenArchiveId((current) => (current === id ? null : id))}
    isResponsable={isResponsable}
    onDelete={removePeriod}
  />
))
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
