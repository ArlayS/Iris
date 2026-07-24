import { ClipboardCheck, LoaderCircle, ShieldCheck, UsersRound } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, getErrorMessage } from "../api/client";


export default function AdminDashboardPage() {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/admin/overview")
      .then((response) => setOverview(response.data))
      .catch((requestError) => setError(getErrorMessage(requestError)));
  }, []);

  if (error) {
    return <section className="page-content admin-page" data-testid="admin-access-error"><p className="admin-error">{error}</p></section>;
  }

  if (!overview) {
    return <div className="loading-page" data-testid="admin-loading"><LoaderCircle className="spin" size={26} /> Chargement de la vue d’ensemble…</div>;
  }

  return (
    <section className="page-content admin-page" data-testid="admin-dashboard-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ADMINISTRATION · VUE PROTÉGÉE</p>
          <h1>Une vue sereine sur l’équipe.</h1>
        </div>
        <span className="admin-protection" data-testid="admin-role-protection"><ShieldCheck size={17} /> Rôle administrateur vérifié</span>
      </header>

      <div className="admin-metrics" data-testid="admin-summary-metrics">
        <div><UsersRound size={19} /><span>Helpers autorisés</span><strong data-testid="admin-helper-count">{overview.total_helpers}</strong></div>
        <div><ClipboardCheck size={19} /><span>Suivis en cours</span><strong data-testid="admin-active-ticket-count">{overview.active_tickets}</strong></div>
        <div><ShieldCheck size={19} /><span>À attribuer</span><strong data-testid="admin-unassigned-ticket-count">{overview.unassigned_tickets}</strong></div>
      </div>

      <section className="admin-helper-grid" data-testid="admin-helper-overview-list">
        {overview.helpers.map((item) => (
          <article className="admin-helper-card" key={item.helper.id} data-testid={`admin-helper-card-${item.helper.id}`}>
            <header>
              <span className="admin-avatar">
                {item.helper.avatar_url ? <img src={item.helper.avatar_url} alt="" /> : item.helper.username.slice(0, 1).toUpperCase()}
              </span>
              <span><h2>{item.helper.display_name || item.helper.username}</h2><p data-testid={`admin-helper-id-${item.helper.id}`}>ID · {item.helper.id}</p></span>
            </header>
            <div className="admin-helper-counts"><span>{item.assigned_count} attribué{item.assigned_count > 1 ? "s" : ""}</span><b>{item.active_count} actif{item.active_count > 1 ? "s" : ""}</b></div>
            <details data-testid={`admin-helper-ticket-details-${item.helper.id}`}>
              <summary>Voir les dossiers attribués</summary>
              {item.tickets.length === 0 ? <p className="admin-empty">Aucun dossier attribué.</p> : item.tickets.map((ticket) => <Link key={ticket.id} to={`/tickets/${ticket.id}`} data-testid={`admin-ticket-link-${ticket.id}`}>{ticket.member.display_name || ticket.member.username}<span>{ticket.follow_up_status}</span></Link>)}
            </details>
          </article>
        ))}
      </section>
    </section>
  );
}