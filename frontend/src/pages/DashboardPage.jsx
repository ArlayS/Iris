import { Activity, ArrowRight, FileText, Headphones, Plus, Radio, Sparkles, Users } from "lucide-react";
import { Link } from "react-router-dom";


export default function DashboardPage({ stats, tickets, isDemo }) {
  const latest = tickets[0];
  return (
    <section className="page-content dashboard-page" data-testid="dashboard-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">OPÉRATIONS / TEMPS RÉEL</p>
          <h1>Votre vue d’intervention.</h1>
        </div>
        <Link className="primary-button" to={isDemo && tickets[0] ? `/tickets/${tickets[0].id}` : "/new"} data-testid="dashboard-new-ticket-button">
          <Plus size={17} /> Nouveau ticket
        </Link>
      </header>

      <div className="metrics-grid" data-testid="ticket-statistics">
        <div className="metric-block"><Activity size={18} /><span>Tickets actifs</span><strong data-testid="active-ticket-count">{stats.active_count}</strong></div>
        <div className="metric-block"><FileText size={18} /><span>Messages archivés</span><strong data-testid="message-count">{stats.total_messages}</strong></div>
        <div className="metric-block"><Users size={18} /><span>Dossiers clos</span><strong data-testid="archived-ticket-count">{stats.archived_count}</strong></div>
      </div>

      <section className="command-hero" data-testid="command-hero">
        <div><p className="eyebrow">SIGNAL PRIORITAIRE</p><h2>{latest ? latest.title : "La file est prête."}</h2><p>{latest ? `Dossier ${latest.id} · ${latest.member.display_name || latest.member.username} attend votre attention.` : "Importez un salon Discord pour initier un dossier."}</p></div>
        {latest ? <Link to={`/tickets/${latest.id}`} className="hero-open" data-testid="open-priority-ticket"><span>Ouvrir le dossier</span><ArrowRight size={20} /></Link> : <Radio size={32} />}
      </section>

      <div className="dashboard-grid">
        <section className="activity-pane" data-testid="ticket-activity-panel">
          <div className="section-heading"><span>ACTIVITÉ RÉCENTE</span><span className="live-dot">LIVE SIGNAL</span></div>
          {tickets.length === 0 ? (
            <div className="dashboard-empty" data-testid="dashboard-empty-state">
              <Radio size={28} />
              <p>Votre file est vide.</p>
              <Link to="/new" data-testid="dashboard-empty-new-ticket-link">Synchroniser un premier ticket <ArrowRight size={14} /></Link>
            </div>
          ) : (
            <div className="ticket-table">
              {tickets.slice(0, 8).map((ticket) => (
                <Link to={`/tickets/${ticket.id}`} className="ticket-table-row" key={ticket.id} data-testid={`ticket-row-${ticket.id}`}>
                  <span className="ticket-table-person">
                    {ticket.member.avatar_url && <img src={ticket.member.avatar_url} alt="" />}
                    <strong>{ticket.member.display_name || ticket.member.username}</strong>
                  </span>
                  <span>#{ticket.channel_name}</span>
                  <span>{ticket.message_count} messages</span>
                  <span className={`status-dot ${ticket.status}`}>{ticket.status === "active" ? "ACTIF" : "ARCHIVÉ"}</span>
                </Link>
              ))}
            </div>
          )}
        </section>
        <aside className="system-pane" data-testid="system-status-panel">
          <p className="eyebrow">INTELLIGENCE</p>
          <div><span><Activity size={15} /> Discord API</span><b>{isDemo ? "SIMULÉE" : "PRÊT"}</b></div>
          <div><span><Headphones size={15} /> Comptes-rendus</span><b>{tickets.length}</b></div>
          <div><span>Dernier dossier</span><strong>{latest ? `#${latest.channel_name}` : "—"}</strong></div>
          {isDemo && <div><span><Sparkles size={15} /> Démonstration</span><b>ACTIVE</b></div>}
        </aside>
      </div>
    </section>
  );
}