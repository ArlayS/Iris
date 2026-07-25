import { Archive, Bot, Check, ChevronLeft, FilePlus2, FileText, HeartHandshake, LoaderCircle, Pause, Play, RefreshCw, Save, ShieldCheck, Trash2, UserRoundCheck, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";


const formatTime = (timestamp) => new Date(timestamp).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });


export default function TicketWorkspacePage({ onTicketUpdate, onTicketDeleted, isAdmin, helper }) {
  const { ticketId } = useParams();
  const navigate = useNavigate();
  const [ticket, setTicket] = useState(null);
  const [vocalSummary, setVocalSummary] = useState("");
  const [personTriggers, setPersonTriggers] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [playing, setPlaying] = useState(false);
  const [followUpStatus, setFollowUpStatus] = useState("en attente de réponse");
  const [helpers, setHelpers] = useState([]);
  const [summaryProgress, setSummaryProgress] = useState("");
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [noteTitle, setNoteTitle] = useState("");
  const [noteContent, setNoteContent] = useState("");
  const [addingNote, setAddingNote] = useState(false);

  useEffect(() => {
    const loadTicket = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await api.get(`/tickets/${ticketId}`);
        setTicket(response.data);
        setVocalSummary(response.data.vocal_summary || "");
        setPersonTriggers(response.data.person_triggers || "");
        setFollowUpStatus(response.data.follow_up_status || "en attente de réponse");
      } catch (requestError) {
        setError(getErrorMessage(requestError));
      } finally {
        setLoading(false);
      }
    };
    loadTicket();
  }, [ticketId]);

  useEffect(() => {
    if (!isAdmin) return;
    api.get("/admin/helpers").then((response) => setHelpers(response.data)).catch(() => undefined);
  }, [isAdmin]);

  const save = async () => {
    setSaving(true);
    try {
      const response = await api.patch(`/tickets/${ticketId}`, {
        vocal_summary: vocalSummary,
        follow_up_status: followUpStatus,
        person_triggers: personTriggers,
      });
      setTicket(response.data);
      onTicketUpdate(response.data);
      toast.success("Dossier enregistré.");
    } catch (requestError) {
      toast.error(getErrorMessage(requestError));
    } finally {
      setSaving(false);
    }
  };

  const addNote = async (event) => {
    event.preventDefault();
    if (!noteTitle.trim() || !noteContent.trim()) return;
    setAddingNote(true);
    try {
      const response = await api.post(`/tickets/${ticketId}/notes`, { title: noteTitle, content: noteContent });
      setTicket((current) => ({ ...current, notes_entries: [...(current.notes_entries || []), response.data] }));
      setNoteTitle("");
      setNoteContent("");
      toast.success("Note ajoutée.");
    } catch (requestError) {
      toast.error(getErrorMessage(requestError));
    } finally {
      setAddingNote(false);
    }
  };

  const deleteNote = async (noteId) => {
    try {
      await api.delete(`/tickets/${ticketId}/notes/${noteId}`);
      setTicket((current) => ({ ...current, notes_entries: current.notes_entries.filter((note) => note.id !== noteId) }));
      toast.success("Note supprimée.");
    } catch (requestError) {
      toast.error(getErrorMessage(requestError));
    }
  };

  const deleteTicket = async () => {
    if (!window.confirm("Supprimer définitivement ce dossier et sa transcription ? Cette action est irréversible.")) return;
    try {
      await api.delete(`/admin/tickets/${ticketId}`);
      onTicketDeleted(ticketId);
      toast.success("Dossier supprimé.");
      navigate("/");
    } catch (requestError) {
      toast.error(getErrorMessage(requestError));
    }
  };

  const sync = async () => {
    setSyncing(true);
    try {
      const response = await api.post(`/tickets/${ticketId}/sync`);
      setTicket(response.data);
      onTicketUpdate(response.data);
      toast.success("Transcription actualisée.");
    } catch (requestError) {
      toast.error(getErrorMessage(requestError));
    } finally {
      setSyncing(false);
    }
  };

  const archive = async () => {
    try {
      const response = await api.patch(`/tickets/${ticketId}`, { status: ticket.status === "active" ? "archived" : "active" });
      setTicket(response.data);
      onTicketUpdate(response.data);
      toast.success(response.data.status === "archived" ? "Ticket archivé." : "Ticket réactivé.");
    } catch (requestError) {
      toast.error(getErrorMessage(requestError));
    }
  };

  const assignHelper = async (helperId) => {
    try {
      const response = await api.patch(`/admin/tickets/${ticketId}/assignment`, { helper_id: helperId || null });
      setTicket(response.data);
      onTicketUpdate(response.data);
      toast.success("Helper principal mis à jour.");
    } catch (requestError) {
      toast.error(getErrorMessage(requestError));
    }
  };

  const generateSummary = async () => {
    setGeneratingSummary(true);
    setSummaryProgress("Connexion à Gemini…");
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/tickets/${ticketId}/ai-summary/stream`, { method: "POST", credentials: "include" });
      if (!response.ok || !response.body) throw new Error("La génération du résumé est indisponible.");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        events.forEach((eventBlock) => {
          const eventType = eventBlock.match(/^event: (.+)$/m)?.[1];
          const data = eventBlock.match(/^data: (.+)$/m)?.[1];
          if (!data) return;
          const payload = JSON.parse(data);
          if (eventType === "progress") setSummaryProgress(payload.message);
          if (eventType === "complete") {
            setTicket((current) => ({ ...current, ai_summary: payload }));
            setSummaryProgress("");
            toast.success("Résumé Gemini enregistré.");
          }
          if (eventType === "error") throw new Error(payload.message);
        });
      }
    } catch (requestError) {
      toast.error(requestError.message || "La génération Gemini a échoué.");
    } finally {
      setGeneratingSummary(false);
      setSummaryProgress("");
    }
  };

  if (loading) return <div className="loading-page" data-testid="ticket-loading"><LoaderCircle className="spin" size={26} /> Chargement du dossier…</div>;
  if (error || !ticket) return <div className="loading-page error-page" data-testid="ticket-load-error">{error || "Ticket introuvable."}</div>;

  const waveform = [38, 66, 44, 82, 54, 91, 47, 73, 35, 63, 86, 52, 76, 43, 68, 94, 57, 71, 39, 62, 83, 49, 74, 45];

  return (
    <section className="workspace-page" data-testid="ticket-workspace-page">
      <header className="workspace-header">
        <div className="workspace-title">
          <Link to="/" className="back-link" data-testid="ticket-back-link"><ChevronLeft size={16} /> Tickets</Link>
          <div className="member-title" data-testid="ticket-member-header">
            <img src={ticket.member.avatar_url} alt="" />
            <span><p>{ticket.id} · ESPACE CONFIDENTIEL</p><h1>{ticket.member.display_name || ticket.member.username}</h1></span>
          </div>
        </div>
        <div className="workspace-actions">
          <button className="secondary-button" disabled={syncing} onClick={sync} type="button" data-testid="sync-ticket-button">
            {syncing ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />} Synchroniser
          </button>
          <button className="secondary-button" onClick={archive} type="button" data-testid="archive-ticket-button"><Archive size={16} /> {ticket.status === "active" ? "Archiver" : "Réactiver"}</button>
          {isAdmin && <button className="danger-button" onClick={deleteTicket} type="button" data-testid="delete-ticket-button"><Trash2 size={16} /> Supprimer</button>}
          <button className="primary-button" disabled={saving} onClick={save} type="button" data-testid="save-ticket-button">
            {saving ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />} Enregistrer
          </button>
        </div>
      </header>

      <div className="ticket-meta" data-testid="ticket-metadata">
        <span>DOSSIER PRIVÉ · {ticket.id}</span>
        <span>{ticket.message_count} ÉCHANGES</span>
        <span>OUVERT LE · {ticket.created_at ? formatTime(ticket.created_at) : "—"}</span>
        <label className="follow-up-control" htmlFor="follow-up-status">STATUT DE SUIVI
          <select id="follow-up-status" value={followUpStatus} onChange={(event) => setFollowUpStatus(event.target.value)} data-testid="follow-up-status-select">
            <option value="en attente de réponse">En attente de réponse</option>
            <option value="en cours">En cours</option>
            <option value="à conclure">À conclure</option>
          </select>
        </label>
      </div>

      <section className="ticket-tools-band" data-testid="ticket-tools-band">
        <div className="assignment-widget" data-testid="helper-assignment-panel">
          <span><UserRoundCheck size={16} /> AIDÉ PAR</span>
          {isAdmin ? <select value={ticket.assigned_helper?.id || ""} onChange={(event) => assignHelper(event.target.value)} data-testid="helper-assignment-select"><option value="">Non attribué</option>{helpers.map((helper) => <option value={helper.id} key={helper.id}>{helper.display_name || helper.username} · {helper.id}</option>)}</select> : <b data-testid="assigned-helper-readonly">{ticket.assigned_helper ? `${ticket.assigned_helper.display_name || ticket.assigned_helper.username} · ${ticket.assigned_helper.id}` : "Non attribué"}</b>}
        </div>
        <div className="ai-notice" data-testid="gemini-privacy-notice"><Bot size={16} /> Gemini synthétise uniquement le contenu de ce dossier, sans diagnostic.</div>
      </section>

      <div className="workspace-grid">
        <section className="workspace-column transcript-column" data-testid="transcript-panel">
          <div className="column-header"><span><HeartHandshake size={16} /> ÉCOUTE</span><b>{ticket.message_count}</b></div>
          <div className="transcript-scroll">
            {ticket.transcript.length === 0 && <p className="empty-transcript" data-testid="empty-transcript">Aucun message dans ce salon.</p>}
            {ticket.transcript.map((message) => (
              <article className={`transcript-message ${message.author.id === "iris-demo-helper" ? "helper-message" : "member-message"}`} key={message.id} data-testid={`transcript-message-${message.id}`}>
                <img src={message.author.avatar_url} alt="" />
                <div>
                  <div className="message-line"><strong>{message.author.display_name || message.author.username}</strong><time>{formatTime(message.timestamp)}</time></div>
                  {message.content && <p>{message.content}</p>}
                  {message.attachments.map((attachment) => <a href={attachment.url} key={attachment.id} target="_blank" rel="noreferrer" data-testid={`attachment-${attachment.id}`}>{attachment.filename}</a>)}
                </div>
              </article>
            ))}
          </div>
        </section>
        <aside className="intelligence-panel" data-testid="vocal-panel">
          <section className="ai-summary-widget" data-testid="ai-summary-panel">
            <div className="intelligence-label"><span><Bot size={15} /> RÉSUMÉ GEMINI</span><b>CONFIDENTIEL</b></div>
            {ticket.ai_summary ? <div className="summary-content" data-testid="ai-summary-content"><div><strong>Contexte</strong><p>{ticket.ai_summary.context}</p></div><div><strong>Besoins exprimés</strong><p>{ticket.ai_summary.expressed_needs}</p></div><div><strong>Actions</strong><p>{ticket.ai_summary.actions}</p></div><div><strong>Prochain suivi</strong><p>{ticket.ai_summary.next_follow_up}</p></div></div> : <p className="summary-empty" data-testid="ai-summary-empty">Aucune synthèse générée pour le moment.</p>}
            <button className="gemini-summary-button" type="button" onClick={generateSummary} disabled={generatingSummary} data-testid="generate-ai-summary-button"><Bot size={16} /> {generatingSummary ? summaryProgress || "Génération…" : "Générer le résumé"}</button>
          </section>
          <section className="person-triggers-widget" data-testid="person-triggers-panel">
            <div className="intelligence-label"><span><HeartHandshake size={15} /> TRIGGERS DE LA PERSONNE</span><b>CONFIDENTIEL</b></div>
            <p>Repères renseignés par l’aidant pour adapter l’écoute.</p>
            <textarea value={personTriggers} onChange={(event) => setPersonTriggers(event.target.value)} placeholder="Situations, sujets ou formulations sensibles pour cette personne…" data-testid="person-triggers-input" />
          </section>
          <div className="vocal-widget">
            <div className="intelligence-label"><span><Volume2 size={15} /> COMPTE-RENDU VOCAL</span><b>PRIVÉ</b></div>
            <p className="vocal-title">Repères de l’échange</p>
            <div className="vocal-player">
              <button className="play-control" type="button" onClick={() => setPlaying((current) => !current)} data-testid="vocal-play-button" aria-label="Lire le compte-rendu vocal">
                {playing ? <Pause size={17} fill="currentColor" /> : <Play size={17} fill="currentColor" />}
              </button>
              <div className={`waveform ${playing ? "is-playing" : ""}`} data-testid="vocal-waveform">
                {waveform.map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}
              </div>
              <span data-testid="vocal-duration">{ticket.id === "TKT-0891" ? "01:12" : ticket.id === "TKT-0890" ? "00:45" : "02:03"}</span>
            </div>
            <textarea
              aria-label="Compte-rendu vocal"
              onChange={(event) => setVocalSummary(event.target.value)}
              placeholder="Synthèse vocale…"
              value={vocalSummary}
              data-testid="ticket-vocal-input"
            />
          </div>
          <section className="notes-widget" data-testid="notes-panel">
            <div className="column-header"><span><FileText size={16} /> NOTES PRIVÉES</span><b><Check size={15} /></b></div>
            <div className="notes-stack" data-testid="ticket-notes-list">
              {ticket.notes && <article className="ticket-note-card legacy-note" data-testid="legacy-ticket-note"><h3>Note générale</h3><p>{ticket.notes}</p></article>}
              {(ticket.notes_entries || []).map((note) => <article className="ticket-note-card" key={note.id} data-testid={`ticket-note-${note.id}`}><header><div><h3>{note.title}</h3><p>{note.author.display_name || note.author.username} · {formatTime(note.updated_at)}</p></div>{(isAdmin || note.author.id === helper.id) && <button type="button" onClick={() => deleteNote(note.id)} data-testid={`delete-note-${note.id}`} aria-label="Supprimer la note"><Trash2 size={15} /></button>}</header><p>{note.content}</p></article>)}
            </div>
            <form className="new-note-form" onSubmit={addNote} data-testid="new-ticket-note-form"><input value={noteTitle} onChange={(event) => setNoteTitle(event.target.value)} placeholder="Titre de la note" maxLength={120} data-testid="ticket-note-title-input" /><textarea value={noteContent} onChange={(event) => setNoteContent(event.target.value)} placeholder="Rédiger une nouvelle note privée…" data-testid="ticket-note-content-input" /><button type="submit" disabled={addingNote} data-testid="add-ticket-note-button"><FilePlus2 size={15} /> {addingNote ? "Ajout…" : "Ajouter la note"}</button></form>
            <p className="editor-foot"><ShieldCheck size={13} /> Visible uniquement dans Iris</p>
          </section>
        </aside>
      </div>
    </section>
  );
}