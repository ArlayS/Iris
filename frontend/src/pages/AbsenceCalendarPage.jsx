import { useEffect, useState } from "react";
import { DayPicker } from "react-day-picker";
import "react-day-picker/dist/style.css";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";


function toIsoDate(date) {
  return date.toISOString().slice(0, 10);
}

export default function AbsenceCalendarPage() {
  const [absences, setAbsences] = useState([]);
  const [range, setRange] = useState();
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const loadAbsences = async () => {
    try {
      const response = await api.get("/staff/absences");
      setAbsences(response.data);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAbsences();
  }, []);

  const submitAbsence = async (event) => {
    event.preventDefault();
    if (!range?.from) {
      toast.error("Sélectionnez au moins une date.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await api.post("/staff/absences", {
        start_date: toIsoDate(range.from),
        end_date: toIsoDate(range.to || range.from),
        reason,
      });
      setAbsences((current) => [...current, response.data].sort((a, b) => a.start_date.localeCompare(b.start_date)));
      setRange(undefined);
      setReason("");
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

  return (
    <section className="page-content staff-page" data-testid="absence-calendar-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>Calendrier des absences</h1>
        </div>
      </header>

      <div className="staff-grid">
        <form className="absence-form" onSubmit={submitAbsence}>
          <DayPicker mode="range" selected={range} onSelect={setRange} numberOfMonths={1} weekStartsOn={1} />
          <label>
            Motif (optionnel)
            <textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} rows={3} />
          </label>
          <button className="calm-primary-button" type="submit" disabled={submitting}>
            {submitting ? "Enregistrement…" : "Ajouter l’absence"}
          </button>
        </form>

        <div className="absence-list">
          <p className="eyebrow">ABSENCES ENREGISTRÉES</p>
          {loading ? (
            <p>Chargement…</p>
          ) : absences.length === 0 ? (
            <p>Aucune absence enregistrée.</p>
          ) : (
            absences.map((entry) => (
              <div className="absence-row" key={entry.id}>
                <span className="helper-avatar">
                  {entry.helper.avatar_url ? <img src={entry.helper.avatar_url} alt="" /> : null}
                </span>
                <div>
                  <strong>{entry.helper.display_name || entry.helper.username}</strong>
                  <small>{entry.start_date}{entry.end_date !== entry.start_date ? ` → ${entry.end_date}` : ""}</small>
                  {entry.reason && <p>{entry.reason}</p>}
                </div>
                <button type="button" className="icon-button" onClick={() => removeAbsence(entry.id)} aria-label="Supprimer l’absence">
                  <Trash2 size={16} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}
