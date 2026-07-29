import { useEffect, useMemo, useState } from "react";
import {
  addDays, addMonths, endOfMonth, endOfWeek, format, isSameDay, isSameMonth,
  isWithinInterval, parseISO, startOfMonth, startOfWeek, subMonths,
} from "date-fns";
import { fr } from "date-fns/locale";
import { Link } from "react-router-dom";
import { ArrowUpRight, ChevronLeft, ChevronRight, ClipboardList, FolderKanban, X } from "lucide-react";
import { toast } from "sonner";
import { api, getErrorMessage } from "../api/client";

const WEEKDAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

function toIsoDate(date) {
  return format(date, "yyyy-MM-dd");
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const TASK_LABELS = {
  a_faire: "À faire",
  en_cours: "En cours",
  rendu: "Rendue",
  valide: "Validée",
};

export default function ProjectCalendarPage() {
  const [projects, setProjects] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [viewedDay, setViewedDay] = useState(null);

  useEffect(() => {
    let isMounted = true;
    api
      .get("/animateur/calendar-events")
      .then((response) => {
        if (!isMounted) return;
        setProjects(response.data.projects);
        setTasks(response.data.tasks);
      })
      .catch((error) => toast.error(getErrorMessage(error)))
      .finally(() => { if (isMounted) setLoading(false); });
    return () => { isMounted = false; };
  }, []);

  const days = useMemo(() => {
    const start = startOfWeek(startOfMonth(currentMonth), { weekStartsOn: 1 });
    const end = endOfWeek(endOfMonth(currentMonth), { weekStartsOn: 1 });
    const result = [];
    let cursor = start;
    while (cursor <= end) {
      result.push(cursor);
      cursor = addDays(cursor, 1);
    }
    return result;
  }, [currentMonth]);

  
const today = toIsoDate(new Date());
const upcomingProjects = [...projects]
  .filter((project) => !project.end_date || project.end_date >= today)
  .sort((a, b) => a.start_date.localeCompare(b.start_date))
  .slice(0, 8);
const projectsByDay = useMemo(() => {
    const map = new Map();
    for (const project of projects) {
      const start = parseISO(project.start_date);
      const end = project.end_date ? parseISO(project.end_date) : start;
      for (const day of days) {
        const within = isWithinInterval(day, { start, end }) || isSameDay(day, start) || isSameDay(day, end);
        if (within) {
          const key = toIsoDate(day);
          if (!map.has(key)) map.set(key, []);
          map.get(key).push(project);
        }
      }
    }
    return map;
  }, [projects, days]);

  const tasksByDay = useMemo(() => {
    const map = new Map();
    for (const task of tasks) {
      if (!task.due_date) continue;
      if (!map.has(task.due_date)) map.set(task.due_date, []);
      map.get(task.due_date).push(task);
    }
    return map;
  }, [tasks]);

  const viewedDayProjects = viewedDay ? projectsByDay.get(toIsoDate(viewedDay)) ?? [] : [];
  const viewedDayTasks = viewedDay ? tasksByDay.get(toIsoDate(viewedDay)) ?? [] : [];

  const upcomingTasks = [...tasks]
    .filter((task) => task.status !== "valide")
    .sort((a, b) => a.due_date.localeCompare(b.due_date))
    .slice(0, 8);

  return (
    <section className="page-content staff-page" data-testid="project-calendar-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE ANIMATEUR</p>
          <h1>Calendrier des projets.</h1>
        </div>
      </header>

      <div className="staff-grid">
        <div className="absence-calendar">
          <div className="absence-calendar-header">
            <h2>{capitalize(format(currentMonth, "MMMM yyyy", { locale: fr }))}</h2>
            <div className="absence-calendar-nav">
              <button type="button" onClick={() => setCurrentMonth((current) => subMonths(current, 1))} aria-label="Mois précédent">
                <ChevronLeft size={16} />
              </button>
              <button type="button" onClick={() => setCurrentMonth(new Date())}>Aujourd'hui</button>
              <button type="button" onClick={() => setCurrentMonth((current) => addMonths(current, 1))} aria-label="Mois suivant">
                <ChevronRight size={16} />
              </button>
            </div>
          </div>

          <div className="absence-calendar-weekdays">
            {WEEKDAYS.map((day) => <span key={day}>{day}</span>)}
          </div>

          <div className="absence-calendar-grid">
            {days.map((day) => {
              const key = toIsoDate(day);
              const dayProjects = projectsByDay.get(key);
              const dayTasks = tasksByDay.get(key);
              const inCurrentMonth = isSameMonth(day, currentMonth);
              const isToday = isSameDay(day, new Date());
              const isViewed = viewedDay && isSameDay(day, viewedDay);

              const classNames = ["absence-day"];
              if (!inCurrentMonth) classNames.push("is-outside");
              if (isToday) classNames.push("is-today");
              if (isViewed) classNames.push("is-viewed");

              return (
                <button
                  type="button"
                  key={key}
                  className={classNames.join(" ")}
                  onClick={() => setViewedDay(day)}
                >
                  <span className="absence-day-number">{format(day, "d")}</span>
                  {dayProjects?.length > 0 && (
  <span className="absence-day-events">
    {dayProjects.slice(0, 2).map((project) => (
      <span key={project.id} className="absence-day-event is-project" title={project.title}>
        {project.title}
      </span>
    ))}
    {dayProjects.length > 2 && <span className="absence-day-event is-more">+{dayProjects.length - 2}</span>}
  </span>
)}
                  {dayTasks?.length > 0 && (
                    <span className="absence-day-events">
                      {dayTasks.slice(0, 2).map((task) => (
                        <span
                          key={task.id}
                          className={`absence-day-event is-task ${task.status === "valide" ? "is-done" : ""}`}
                          title={task.title}
                        >
                          {task.title}
                        </span>
                      ))}
                      {dayTasks.length > 2 && <span className="absence-day-event is-more">+{dayTasks.length - 2}</span>}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {viewedDay && (
            <div className="absence-detail-panel">
              <div>
                <strong>{capitalize(format(viewedDay, "EEEE d MMMM yyyy", { locale: fr }))}</strong>
                <button type="button" className="icon-button" onClick={() => setViewedDay(null)} aria-label="Fermer">
                  <X size={15} />
                </button>
              </div>

              {viewedDayProjects.length === 0 && viewedDayTasks.length === 0 ? (
                <p className="resources-empty">Rien de prévu ce jour.</p>
              ) : (
                <div className="absence-detail-list">
                  {viewedDayProjects.map((project) => (
                    <div className="absence-detail-row absence-meeting-info-row" key={project.id}>
                      <span className="absence-meeting-icon"><FolderKanban size={16} /></span>
                      <div>
                        <strong>{project.title}</strong>
                        <small>{project.start_date} → {project.end_date}</small>
                      </div>
                      <Link className="icon-button absence-meeting-open" to={`/animateur/projects/${project.id}`}>
                        <ArrowUpRight size={16} />
                      </Link>
                    </div>
                  ))}
                  {viewedDayTasks.map((task) => (
                    <div className="absence-detail-row absence-meeting-info-row" key={task.id}>
                      <span className="absence-meeting-icon"><ClipboardList size={16} /></span>
                      <div>
                        <strong>{task.title}</strong>
                        <small>Assigné à {task.assignee.display_name || task.assignee.username}</small>
                        <span className={`meeting-status-badge ${task.status === "valide" ? "is-done" : "is-pending"}`}>
                          {TASK_LABELS[task.status]}
                        </span>
                      </div>
                      <Link className="icon-button absence-meeting-open" to={`/animateur/projects/${task.project_id}`}>
                        <ArrowUpRight size={16} />
                      </Link>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
<aside className="absence-upcoming">
  <p className="eyebrow">PROJETS EN COURS</p>
  {loading ? (
    <p className="resources-empty">Chargement…</p>
  ) : upcomingProjects.length === 0 ? (
    <p className="resources-empty">Aucun projet actif.</p>
  ) : (
    upcomingProjects.map((project) => (
      <Link
        key={project.id}
        to={`/animateur/projects/${project.id}`}
        className="absence-upcoming-row"
        style={{ textDecoration: "none" }}
      >
        <span className="absence-meeting-icon"><FolderKanban size={16} /></span>
        <div>
          <strong>{project.title}</strong>
          <small>{project.start_date} → {project.end_date || "…"}</small>
        </div>
      </Link>
    ))
  )}
</aside>
        <aside className="absence-upcoming">
          <p className="eyebrow">TÂCHES À VENIR</p>
          {loading ? (
            <p className="resources-empty">Chargement…</p>
          ) : upcomingTasks.length === 0 ? (
            <p className="resources-empty">Aucune tâche en attente.</p>
          ) : (
            upcomingTasks.map((task) => (
              <div className="absence-upcoming-row" key={task.id}>
                <span className="absence-meeting-icon"><ClipboardList size={16} /></span>
                <div>
                  <strong>{task.title}</strong>
                  <small>{task.due_date} · {task.assignee.display_name || task.assignee.username}</small>
                </div>
              </div>
            ))
          )}
        </aside>
      </div>
    </section>
  );
}
