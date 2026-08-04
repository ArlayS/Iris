import { useState } from "react";
import { Plus } from "lucide-react";

import CreateCasierModal from "../components/CreateCasierModal"; // ou "../components/CreateCasierModal"

export default function ModerationCasierPage() {
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <section className="page-content staff-page moderation-page" data-testid="moderation-casier-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>Modération – Casier</h1>
        </div>

        <div className="dashboard-actions">
          <button
            className="calm-primary-button"
            type="button"
            onClick={() => setCreateOpen(true)}
          >
            <Plus size={17} />
            Créer un casier
          </button>
        </div>
      </header>

      <div className="moderation-placeholder-card">
        <div className="moderation-placeholder-icon">
          <Plus size={20} />
        </div>
        <div>
          <strong>Contenu à venir</strong>
          <p>
            Liste des casiers, filtres, et détail à implémenter ici.
          </p>
        </div>
      </div>

      <CreateCasierModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          // TODO: refresh la liste des casiers
          setCreateOpen(false);
        }}
      />
    </section>
  );
}
