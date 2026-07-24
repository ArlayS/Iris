import { Activity, ArrowRight, FileText, Plus, Radio, Users } from "lucide-react";
import { Link } from "react-router-dom";


export default function DashboardPage({ stats, tickets }) {
  const latest = tickets[0];
  return (
    <section className="page-content dashboard-page" data-testid="dashboard-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">VUE D’ENSEMBLE</p>
          <h1>Command center</h1>
        </div>
        <Link className="primary-button" to="/new" data-testid="dashboard-new-ticket-button">
          <Plus size={17} /> Nouveau ticket
        </Link>
      </header>

      <div className="metrics-grid" data-testid="ticket-statistics">
        <div className="metric-block"><Activity size={18} /><span>Tickets actifs</span><strong data-testid="active-ticket-count">{stats.active_count}</strong></div>
        <div className="metric-block"><FileText size={18} /><span>Messages archivés</span><strong data-testid="message-count">{stats.total_messages}</strong></div>
        <div className="metric-block"><Users size={18} /><span>Dossiers clos</span><strong data-testid="archived-ticket-count">{stats.archived_count}</strong></div>
      </div>

      <div className="dashboard-grid">
        <section className="activity-pane" data-testid="ticket-activity-panel">
          <div className="section-heading"><span>ACTIVITÉ RÉCENTE</span><span className="live-dot">LIVE</span></div>
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
          <p className="eyebrow">SYSTEM STATUS</p>
          <div><span>Discord API</span><b>PRÊT</b></div>
          <div><span>Base de données</span><b>CONNECTÉE</b></div>
          <div><span>Dernier dossier</span><strong>{latest ? `#${latest.channel_name}` : "—"}</strong></div>
        </aside>
      </div>
    </section>
  );
}