import { useState } from "react";
import { ArrowRight, LoaderCircle } from "lucide-react";

import { api, getErrorMessage } from "../api/client";


export default function DemoCaseForm({ onCreated }) {
  const [name, setName] = useState("");
  const [reason, setReason] = useState("");
  const [priority, setPriority] = useState("routine");
  const [followUpStatus, setFollowUpStatus] = useState("à écouter");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await api.post("/tickets/demo", {
        name,
        reason,
        priority,
        follow_up_status: followUpStatus,
      });
      onCreated(response.data);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="case-form" onSubmit={submit} data-testid="complete-case-form">
      <label htmlFor="case-name">Prénom ou pseudonyme</label>
      <input id="case-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Ex. Camille" minLength={2} required data-testid="case-name-input" />
      <label htmlFor="case-reason">Motif de la demande</label>
      <textarea id="case-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Décrivez brièvement le besoin d’écoute…" minLength={3} required data-testid="case-reason-input" />
      <div className="case-form-grid">
        <div>
          <label htmlFor="case-priority">Niveau d’attention</label>
          <select id="case-priority" value={priority} onChange={(event) => setPriority(event.target.value)} data-testid="case-priority-select">
            <option value="routine">À l’écoute</option>
            <option value="prioritaire">Prioritaire</option>
            <option value="urgent">Urgent</option>
          </select>
        </div>
        <div>
          <label htmlFor="case-follow-up">Statut de suivi</label>
          <select id="case-follow-up" value={followUpStatus} onChange={(event) => setFollowUpStatus(event.target.value)} data-testid="case-follow-up-select">
            <option value="à écouter">À écouter</option>
            <option value="en suivi">En suivi</option>
            <option value="stable">Stable</option>
          </select>
        </div>
      </div>
      {error && <p className="form-error" role="alert" data-testid="complete-case-error">{error}</p>}
      <button className="calm-primary-button" disabled={loading} type="submit" data-testid="complete-case-submit-button">
        {loading ? <LoaderCircle className="spin" size={17} /> : <ArrowRight size={17} />}
        {loading ? "Création…" : "Ouvrir le dossier"}
      </button>
    </form>
  );
}