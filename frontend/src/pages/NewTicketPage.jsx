import { ChevronLeft, HeartHandshake, LockKeyhole, NotebookPen } from "lucide-react";
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
          <p className="eyebrow">IMPORT DISCORD</p>
          <h1>Importer un dossier depuis Discord.</h1>
          <p>Saisissez l’ID de la personne et du salon Discord : Iris vérifiera vos accès, récupérera le profil et archivera l’historique complet du salon.</p>
          <div className="process-list">
            <div><HeartHandshake size={18} /><span><b>01 · Profil</b>Vérification du membre sur le serveur</span></div>
            <div><NotebookPen size={18} /><span><b>02 · Historique</b>Import paginé de tous les messages du salon</span></div>
            <div><LockKeyhole size={18} /><span><b>03 · Dossier privé</b>Notes et suivi privés dans Iris</span></div>
          </div>
        </div>
        <NewTicketForm onCreated={created} />
      </div>
    </section>
  );
}