import { ArrowRight, BookHeart, HeartHandshake, LoaderCircle, Plus, Radio, ShieldCheck, Users } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { toast } from "sonner";


export default function DashboardPage({ stats, tickets, isDemo, onQuickCreate }) {
  const latest = tickets[0];
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);

  const createQuickCase = async () => {
    setCreating(true);
    try {
      const ticket = await onQuickCreate();
      navigate(`/tickets/${ticket.id}`);
    } catch (error) {
      toast.error("Impossible de créer le dossier de démonstration.");
      setCreating(false);
    }
  };
  return (
    <section className="page-content dashboard-page" data-testid="dashboard-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE HELPERS</p>
          <h1>Un suivi attentif, à votre rythme.</h1>
        </div>
        <div className="dashboard-actions">
          <button className="quick-case-button" type="button" onClick={createQuickCase} disabled={!isDemo || creating} data-testid="quick-demo-case-button">
            {creating ? <LoaderCircle className="spin" size={17} /> : <HeartHandshake size={17} />}
            Créer un suivi test
          </button>
          <Link className="calm-primary-button" to="/new" data-testid="complete-case-form-button"><Plus size={17} /> Formulaire complet</Link>
        </div>
      </header>

      <div className="metrics-grid" data-testid="ticket-statistics">
        <div className="metric-block"><HeartHandshake size={18} /><span>Suivis ouverts</span><strong data-testid="active-ticket-count">{stats.active_count}</strong></div>
        <div className="metric-block"><BookHeart size={18} /><span>Échanges consignés</span><strong data-testid="message-count">{stats.total_messages}</strong></div>
        <div className="metric-block"><ShieldCheck size={18} /><span>Suivis stabilisés</span><strong data-testid="archived-ticket-count">{stats.archived_count}</strong></div>
      </div>

      <section className="care-hero" data-testid="command-hero">
        <div><p className="eyebrow">À ACCUEILLIR</p><h2>{latest ? latest.title : "Un espace prêt à écouter."}</h2><p>{latest ? `Dossier ${latest.id} · ${latest.member.display_name || latest.member.username}. Ouvrez le dossier lorsque vous êtes disponible.` : "Créez un suivi test ou utilisez le formulaire pour démarrer."}</p></div>
        {latest ? <Link to={`/tickets/${latest.id}`} className="care-open" data-testid="open-priority-ticket"><span>Ouvrir le suivi</span><ArrowRight size={20} /></Link> : <Radio size={32} />}
      </section>

      <div className="dashboard-grid">
        <section className="activity-pane" data-testid="ticket-activity-panel">
          <div className="section-heading"><span>SUIVIS EN COURS</span><span className="live-dot">CONFIDENTIEL</span></div>
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
                  <span>{ticket.follow_up_status}</span>
                  <span>{ticket.message_count} échanges</span>
                  <span className={`status-dot ${ticket.status}`}>{ticket.status === "active" ? "EN SUIVI" : "STABLE"}</span>
                </Link>
              ))}
            </div>
          )}
        </section>
        <aside className="system-pane" data-testid="system-status-panel">
          <p className="eyebrow">REPÈRES</p>
          <div><span><HeartHandshake size={15} /> Écoute active</span><b>{isDemo ? "DÉMO" : "PRÊT"}</b></div>
          <div><span><BookHeart size={15} /> Notes privées</span><b>{tickets.length}</b></div>
          <div><span>Dernier suivi</span><strong>{latest ? latest.member.display_name || latest.member.username : "—"}</strong></div>
        </aside>
      </div>
    </section>
  );
}