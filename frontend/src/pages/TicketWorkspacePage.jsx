import { Archive, Check, ChevronLeft, FileText, LoaderCircle, MessageSquareText, RefreshCw, Save, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";


const formatTime = (timestamp) => new Date(timestamp).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });


export default function TicketWorkspacePage({ onTicketUpdate }) {
  const { ticketId } = useParams();
  const [ticket, setTicket] = useState(null);
  const [notes, setNotes] = useState("");
  const [vocalSummary, setVocalSummary] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const loadTicket = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await api.get(`/tickets/${ticketId}`);
        setTicket(response.data);
        setNotes(response.data.notes || "");
        setVocalSummary(response.data.vocal_summary || "");
      } catch (requestError) {
        setError(getErrorMessage(requestError));
      } finally {
        setLoading(false);
      }
    };
    loadTicket();
  }, [ticketId]);

  const save = async () => {
    setSaving(true);
    try {
      const response = await api.patch(`/tickets/${ticketId}`, { notes, vocal_summary: vocalSummary });
      setTicket(response.data);
      onTicketUpdate(response.data);
      toast.success("Dossier enregistré.");
    } catch (requestError) {
      toast.error(getErrorMessage(requestError));
    } finally {
      setSaving(false);
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

  if (loading) return <div className="loading-page" data-testid="ticket-loading"><LoaderCircle className="spin" size={26} /> Chargement du dossier…</div>;
  if (error || !ticket) return <div className="loading-page error-page" data-testid="ticket-load-error">{error || "Ticket introuvable."}</div>;

  return (
    <section className="workspace-page" data-testid="ticket-workspace-page">
      <header className="workspace-header">
        <div className="workspace-title">
          <Link to="/" className="back-link" data-testid="ticket-back-link"><ChevronLeft size={16} /> Tickets</Link>
          <div className="member-title" data-testid="ticket-member-header">
            <img src={ticket.member.avatar_url} alt="" />
            <span><p>#{ticket.channel_name}</p><h1>{ticket.member.display_name || ticket.member.username}</h1></span>
          </div>
        </div>
        <div className="workspace-actions">
          <button className="secondary-button" disabled={syncing} onClick={sync} type="button" data-testid="sync-ticket-button">
            {syncing ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />} Synchroniser
          </button>
          <button className="secondary-button" onClick={archive} type="button" data-testid="archive-ticket-button"><Archive size={16} /> {ticket.status === "active" ? "Archiver" : "Réactiver"}</button>
          <button className="primary-button" disabled={saving} onClick={save} type="button" data-testid="save-ticket-button">
            {saving ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />} Enregistrer
          </button>
        </div>
      </header>

      <div className="ticket-meta" data-testid="ticket-metadata"><span>MEMBRE · {ticket.member.id}</span><span>CANAL · {ticket.channel_id}</span><span>{ticket.message_count} MESSAGES</span><span>SYNC · {ticket.last_synced_at ? formatTime(ticket.last_synced_at) : "—"}</span></div>

      <div className="workspace-grid">
        <section className="workspace-column transcript-column" data-testid="transcript-panel">
          <div className="column-header"><span><MessageSquareText size={16} /> TRANSCRIPTION</span><b>{ticket.message_count}</b></div>
          <div className="transcript-scroll">
            {ticket.transcript.length === 0 && <p className="empty-transcript" data-testid="empty-transcript">Aucun message dans ce salon.</p>}
            {ticket.transcript.map((message) => (
              <article className="transcript-message" key={message.id} data-testid={`transcript-message-${message.id}`}>
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
        <section className="workspace-column editor-column" data-testid="notes-panel">
          <div className="column-header"><span><FileText size={16} /> NOTE INTERNE</span><b><Check size={15} /></b></div>
          <textarea
            aria-label="Note interne"
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Laissez une note utile pour l’équipe…"
            value={notes}
            data-testid="ticket-notes-input"
          />
          <p className="editor-foot">Visible uniquement dans Iris</p>
        </section>
        <section className="workspace-column editor-column" data-testid="vocal-panel">
          <div className="column-header"><span><Volume2 size={16} /> COMPTE-RENDU VOCAL</span><b><Check size={15} /></b></div>
          <textarea
            aria-label="Compte-rendu vocal"
            onChange={(event) => setVocalSummary(event.target.value)}
            placeholder="Consignez les éléments évoqués en vocal…"
            value={vocalSummary}
            data-testid="ticket-vocal-input"
          />
          <p className="editor-foot">Synthèse de l’assistance vocale</p>
        </section>
      </div>
    </section>
  );
}