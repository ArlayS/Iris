import { Archive, Check, ChevronLeft, FileText, LoaderCircle, MessageSquareText, Pause, Play, RefreshCw, Save, ShieldCheck, Sparkles, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";


const formatTime = (timestamp) => new Date(timestamp).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });


export default function TicketWorkspacePage({ onTicketUpdate, isDemo }) {
  const { ticketId } = useParams();
  const [ticket, setTicket] = useState(null);
  const [notes, setNotes] = useState("");
  const [vocalSummary, setVocalSummary] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [playing, setPlaying] = useState(false);

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

  const waveform = [38, 66, 44, 82, 54, 91, 47, 73, 35, 63, 86, 52, 76, 43, 68, 94, 57, 71, 39, 62, 83, 49, 74, 45];

  return (
    <section className="workspace-page" data-testid="ticket-workspace-page">
      <header className="workspace-header">
        <div className="workspace-title">
          <Link to="/" className="back-link" data-testid="ticket-back-link"><ChevronLeft size={16} /> Tickets</Link>
          <div className="member-title" data-testid="ticket-member-header">
            <img src={ticket.member.avatar_url} alt="" />
            <span><p>{ticket.id} · #{ticket.channel_name}</p><h1>{ticket.member.display_name || ticket.member.username}</h1></span>
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

      <div className="ticket-meta" data-testid="ticket-metadata">
        <span>MEMBRE · {ticket.member.id}</span>
        <span>CANAL · {ticket.channel_id}</span>
        <span>{ticket.message_count} MESSAGES</span>
        <span>SYNC · {ticket.last_synced_at ? formatTime(ticket.last_synced_at) : "—"}</span>
        {isDemo && <span className="workspace-demo-badge"><Sparkles size={12} /> DÉMONSTRATION</span>}
      </div>

      <div className="workspace-grid">
        <section className="workspace-column transcript-column" data-testid="transcript-panel">
          <div className="column-header"><span><MessageSquareText size={16} /> TRANSCRIPTION</span><b>{ticket.message_count}</b></div>
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
          <div className="vocal-widget">
            <div className="intelligence-label"><span><Sparkles size={15} /> INTELLIGENCE VOCALE</span><b>ANALYSE</b></div>
            <p className="vocal-title">Compte-rendu de session</p>
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
            <div className="column-header"><span><FileText size={16} /> NOTE INTERNE</span><b><Check size={15} /></b></div>
            <textarea
              aria-label="Note interne"
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Laissez une note utile pour l’équipe…"
              value={notes}
              data-testid="ticket-notes-input"
            />
            <p className="editor-foot"><ShieldCheck size={13} /> Visible uniquement dans Iris</p>
          </section>
        </aside>
      </div>
    </section>
  );
}