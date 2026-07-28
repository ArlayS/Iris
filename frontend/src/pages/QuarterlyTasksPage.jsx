import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckSquare, ListTodo, Plus, Trash2 } from "lucide-react";
import { api, getErrorMessage } from "../api/client";

export default function QuarterlyTasksPage({ isResponsable }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api
      .get("/staff/tasks")
      .then((response) => setTasks(response.data))
      .catch((error) => toast.error(getErrorMessage(error)))
      .finally(() => setLoading(false));
  }, []);

  const addTask = async (event) => {
    event.preventDefault();
    if (!title.trim()) return;
    setSubmitting(true);
    try {
      const response = await api.post("/staff/tasks", { title: title.trim() });
      setTasks((current) => [response.data, ...current]);
      setTitle("");
      toast.success("Tâche ajoutée.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  const toggleTask = async (task) => {
    try {
      const response = await api.put(`/staff/tasks/${task.id}`, { is_done: !task.is_done });
      setTasks((current) => current.map((item) => (item.id === task.id ? response.data : item)));
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const removeTask = async (taskId) => {
    try {
      await api.delete(`/staff/tasks/${taskId}`);
      setTasks((current) => current.filter((item) => item.id !== taskId));
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  return (
    <section className="page-content dashboard-page" data-testid="quarterly-tasks-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>Tâches trimestrielles</h1>
        </div>
      </header>

      {isResponsable && (
        <form onSubmit={addTask} className="meeting-inline-form" style={{ marginBottom: "24px" }}>
          <input
            className="meeting-inline-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Nouvelle tâche…"
            maxLength={160}
          />
          <button type="submit" className="meeting-inline-submit" disabled={submitting}>
            <Plus size={16} /> Ajouter la tâche
          </button>
        </form>
      )}

      <div className="dashboard-card">
        {loading ? (
          <p className="dashboard-loading">Chargement…</p>
        ) : tasks.length === 0 ? (
          <p className="dashboard-empty">Aucune tâche pour ce trimestre.</p>
        ) : (
          <div className="meetings-list">
            {tasks.map((task) => (
              <div key={task.id} className="meeting-row">
                <button type="button" className="meeting-row-main" onClick={() => toggleTask(task)} style={{ display: "flex", alignItems: "center", gap: "10px", background: "transparent", border: "none", cursor: "pointer", textAlign: "left" }}>
                  {task.is_done ? <CheckSquare size={18} /> : <ListTodo size={18} />}
                  <span style={{ textDecoration: task.is_done ? "line-through" : "none" }}>{task.title}</span>
                </button>
                {isResponsable && (
                  <button type="button" className="icon-btn-danger" onClick={() => removeTask(task.id)} aria-label="Supprimer">
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
