import { useState } from "react";
import { ArrowRight, Hash, LoaderCircle, UserRound } from "lucide-react";

import { api, getErrorMessage } from "../api/client";


export default function NewTicketForm({ onCreated }) {
  const [memberId, setMemberId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const response = await api.post("/tickets", {
        member_id: memberId.trim(),
        channel_id: channelId.trim(),
        title: title.trim() || null,
      });
      onCreated(response.data);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="command-form" onSubmit={submit} data-testid="new-ticket-form">
      <div className="command-row">
        <label htmlFor="member-id" className="command-label">
          <UserRound size={16} /> MEMBRE DISCORD
        </label>
        <input
          autoComplete="off"
          id="member-id"
          inputMode="numeric"
          onChange={(event) => setMemberId(event.target.value)}
          placeholder="ID du membre"
          required
          value={memberId}
          data-testid="member-id-input"
        />
      </div>
      <div className="command-row">
        <label htmlFor="channel-id" className="command-label">
          <Hash size={16} /> SALON DU TICKET
        </label>
        <input
          autoComplete="off"
          id="channel-id"
          inputMode="numeric"
          onChange={(event) => setChannelId(event.target.value)}
          placeholder="ID du salon texte"
          required
          value={channelId}
          data-testid="channel-id-input"
        />
      </div>
      <div className="command-row optional-command-row">
        <label htmlFor="ticket-title" className="command-label">TITRE</label>
        <input
          id="ticket-title"
          maxLength={120}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Optionnel — généré automatiquement"
          value={title}
          data-testid="ticket-title-input"
        />
      </div>
      {error && <p className="form-error" role="alert" data-testid="new-ticket-error">{error}</p>}
      <button className="primary-button" disabled={loading} type="submit" data-testid="create-ticket-button">
        {loading ? <LoaderCircle className="spin" size={17} /> : <ArrowRight size={17} />}
        {loading ? "Synchronisation…" : "Créer le dossier"}
      </button>
    </form>
  );
}