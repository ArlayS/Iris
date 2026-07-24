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
          <p className="eyebrow">{isDemo ? "NOUVEAU SUIVI" : "IMPORT DISCORD"}</p>
          <h1>{isDemo ? "Ouvrir un espace d’écoute." : "Importer un dossier depuis Discord."}</h1>
          <p>{isDemo ? "Chaque dossier est un espace de travail privé pour organiser l’écoute, les notes et le suivi de la personne accompagnée." : "Saisissez l’ID de la personne et du salon Discord : Iris vérifiera vos accès, récupérera le profil et archivera l’historique complet du salon."}</p>
          <div className="process-list">
            <div><HeartHandshake size={18} /><span><b>01 · {isDemo ? "Écoute" : "Profil"}</b>{isDemo ? "Accueillir la demande avec attention" : "Vérification du membre sur le serveur"}</span></div>
            <div><NotebookPen size={18} /><span><b>02 · {isDemo ? "Notes privées" : "Historique"}</b>{isDemo ? "Conserver les repères utiles au suivi" : "Import paginé de tous les messages du salon"}</span></div>
            <div><LockKeyhole size={18} /><span><b>03 · {isDemo ? "Continuité" : "Dossier privé"}</b>{isDemo ? "Mettre à jour le statut de suivi" : "Notes et suivi privés dans Iris"}</span></div>
          </div>
        </div>
        {isDemo ? <DemoCaseForm onCreated={created} /> : <NewTicketForm onCreated={created} />}
      </div>
    </section>
  );
}