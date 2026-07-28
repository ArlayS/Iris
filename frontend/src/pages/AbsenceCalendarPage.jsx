import { useEffect, useMemo, useState } from "react";
import {
  addDays,
  addMonths,
  endOfMonth,
  endOfWeek,
  format,
  isBefore,
  isSameDay,
  isSameMonth,
  isWithinInterval,
  parseISO,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { fr } from "date-fns/locale";
import { ChevronLeft, ChevronRight, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";

const WEEKDAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

function toIsoDate(date) {
  return format(date, "yyyy-MM-dd");
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export default function AbsenceCalendarPage() {
  const [absences, setAbsences] = useState([]);
  const [loading, setLoading] = useState(true);
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [selection, setSelection] = useState(null);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let isMounted = true;
    api
      .get("/staff/absences")
      .then((response) => {
        if (isMounted) setAbsences(response.data);
      })
      .catch((error) => {
        toast.error(getErrorMessage(error));
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });
    return () => {
      isMounted = false;
    };
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

  const absencesByDay = useMemo(() => {
    const map = new Map();
    for (const entry of absences) {
      const start = parseISO(entry.start_date);
      const end = parseISO(entry.end_date);
      for (const day of days) {
        const withinRange =
          isWithinInterval(day, { start, end }) || isSameDay(day, start) || isSameDay(day, end);
        if (withinRange) {
          const key = toIsoDate(day);
          if (!map.has(key)) {
            map.set(key, []);
          }
          map.get(key).push(entry);
        }
      }
    }
    return map;
  }, [absences, days]);

  const handleDayClick = (day) => {
    if (!selection || !selection.start) {
      setSelection({ start: day, end: day });
      return;
    }
    if (isBefore(day, selection.start)) {
      setSelection({ start: day, end: day });
      return;
    }
    setSelection({ start: selection.start, end: day });
  };

  const clearSelection = () => {
    setSelection(null);
    setReason("");
  };

  const submitAbsence = async () => {
    if (!selection) {
      return;
    }
    setSubmitting(true);
    try {
      const response = await api.post("/staff/absences", {
        start_date: toIsoDate(selection.start),
        end_date: toIsoDate(selection.end),
        reason,
      });
      setAbsences((current) => [...current, response.data]);
      clearSelection();
      toast.success("Absence enregistrée.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  const removeAbsence = async (absenceId) => {
    try {
      await api.delete(`/staff/absences/${absenceId}`);
      setAbsences((current) => current.filter((entry) => entry.id !== absenceId));
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const upcoming = [...absences].sort((a, b) => a.start_date.localeCompare(b.start_date));

  return (
    <section className="page-content staff-page" data-testid="absence-calendar-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>Calendrier des absences</h1>
        </div>
      </header>

      <div className="staff-grid">
        <div className="absence-calendar">
          <div className="absence-calendar-header">
            <h2>{capitalize(format(currentMonth, "MMMM yyyy", { locale: fr }))}</h2>
            <div className="absence-calendar-nav">
              <button
                type="button"
                onClick={() => setCurrentMonth((current) => subMonths(current, 1))}
                aria-label="Mois précédent"
              >
                <ChevronLeft size={16} />
              </button>
              <button type="button" onClick={() => setCurrentMonth(new Date())}>
                Aujourd’hui
              </button>
              <button
                type="button"
                onClick={() => setCurrentMonth((current) => addMonths(current, 1))}
                aria-label="Mois suivant"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>

          <div className="absence-calendar-weekdays">
            {WEEKDAYS.map((day) => (
              <span key={day}>{day}</span>
            ))}
          </div>

          <div className="absence-calendar-grid">
            {days.map((day) => {
              const key = toIsoDate(day);
              const dayAbsences = absencesByDay.get(key) || [];
              const inCurrentMonth = isSameMonth(day, currentMonth);
              const isToday = isSameDay(day, new Date());
              const isSelected =
                selection && isWithinInterval(day, { start: selection.start, end: selection.end });

              const classNames = ["absence-day"];
              if (!inCurrentMonth) {
                classNames.push("is-outside");
              }
              if (isToday) {
                classNames.push("is-today");
              }
              if (isSelected) {
                classNames.push("is-selected");
              }

              return (
                <button
                  type="button"
                  key={key}
                  className={classNames.join(" ")}
                  onClick={() => handleDayClick(day)}
                >
                  <span className="absence-day-number">{format(day, "d")}</span>
                  <span className="absence-day-chips">
                    {dayAbsences.slice(0, 2).map((entry) => (
                      <span
                        className="absence-day-chip"
                        key={entry.id}
                        title={entry.helper.display_name || entry.helper.username}
                      >
                        {(entry.helper.display_name || entry.helper.username || "?").charAt(0).toUpperCase()}
                      </span>
                    ))}
                    {dayAbsences.length > 2 && (
                      <span className="absence-day-chip is-more">+{dayAbsences.length - 2}</span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>

          {selection && (
            <div className="absence-confirm-panel">
              <div>
                <strong>
                  {isSameDay(selection.start, selection.end)
                    ? format(selection.start, "d MMMM yyyy", { locale: fr })
                    : `${format(selection.start, "d MMM", { locale: fr })} → ${format(
                        selection.end,
                        "d MMMM yyyy",
                        { locale: fr }
                      )}`}
                </strong>
                <button type="button" className="icon-button" onClick={clearSelection} aria-label="Annuler la sélection">
                  <X size={15} />
                </button>
              </div>
              <textarea
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Motif (optionnel)"
                maxLength={500}
                rows={2}
              />
              <button className="calm-primary-button" type="button" onClick={submitAbsence} disabled={submitting}>
                {submitting ? "Enregistrement…" : "Ajouter l’absence"}
              </button>
            </div>
          )}
        </div>

        <aside className="absence-upcoming">
          <p className="eyebrow">ABSENCES À VENIR</p>
          {loading ? (
            <p className="resources-empty">Chargement…</p>
          ) : upcoming.length === 0 ? (
            <p className="resources-empty">Aucune absence enregistrée.</p>
          ) : (
            upcoming.map((entry) => (
              <div className="absence-upcoming-row" key={entry.id}>
                <span className="absence-day-chip">
                  {(entry.helper.display_name || entry.helper.username || "?").charAt(0).toUpperCase()}
                </span>
                <div>
                  <strong>{entry.helper.display_name || entry.helper.username}</strong>
                  <small>
                    {entry.start_date === entry.end_date
                      ? entry.start_date
                      : `${entry.start_date} → ${entry.end_date}`}
                  </small>
                  {entry.reason && <p>{entry.reason}</p>}
                </div>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => removeAbsence(entry.id)}
                  aria-label="Supprimer l’absence"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))
          )}
        </aside>
      </div>
    </section>
  );
}
