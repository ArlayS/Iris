import { ChevronLeft, Database, Hash, UserRound } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import NewTicketForm from "../components/NewTicketForm";


export default function NewTicketPage({ onCreated }) {
  const navigate = useNavigate();
  const created = (ticket) => {
    onCreated(ticket);
    navigate(`/tickets/${ticket.id}`);
  };

  return (
    <section className="page-content new-ticket-page" data-testid="new-ticket-page">
      <Link className="back-link" to="/" data-testid="new-ticket-back-link"><ChevronLeft size={16} /> Retour au centre</Link>
      <div className="new-ticket-layout">
        <div className="new-ticket-intro">
          <p className="eyebrow">NOUVEAU DOSSIER / 02</p>
          <h1>Importer un ticket Discord.</h1>
          <p>Le système vérifie le membre, récupère le salon et archive l’historique complet du ticket.</p>
          <div className="process-list">
            <div><UserRound size={18} /><span><b>01 · Membre</b>Identification via l’ID Discord</span></div>
            <div><Hash size={18} /><span><b>02 · Salon</b>Contrôle du ticket dans le serveur</span></div>
            <div><Database size={18} /><span><b>03 · Registre</b>Copie locale et consultable</span></div>
          </div>
        </div>
        <NewTicketForm onCreated={created} />
      </div>
    </section>
  );
}