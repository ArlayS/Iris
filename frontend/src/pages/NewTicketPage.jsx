import { ChevronLeft, HeartHandshake, LockKeyhole, NotebookPen } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import NewTicketForm from "../components/NewTicketForm";
import DemoCaseForm from "../components/DemoCaseForm";


export default function NewTicketPage({ onCreated, isDemo }) {
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
          <p className="eyebrow">NOUVEAU SUIVI</p>
          <h1>Ouvrir un espace d’écoute.</h1>
          <p>Chaque dossier est un espace de travail privé pour organiser l’écoute, les notes et le suivi de la personne accompagnée.</p>
          <div className="process-list">
            <div><HeartHandshake size={18} /><span><b>01 · Écoute</b>Accueillir la demande avec attention</span></div>
            <div><NotebookPen size={18} /><span><b>02 · Notes privées</b>Conserver les repères utiles au suivi</span></div>
            <div><LockKeyhole size={18} /><span><b>03 · Continuité</b>Mettre à jour le statut de suivi</span></div>
          </div>
        </div>
        {isDemo ? <DemoCaseForm onCreated={created} /> : <NewTicketForm onCreated={created} />}
      </div>
    </section>
  );
}