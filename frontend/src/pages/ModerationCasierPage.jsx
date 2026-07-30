import { useState } from "react";
import { Plus, ShieldAlert } from "lucide-react";
import CreateCasierModal from "../components/CreateCasierModal";

export default function CasierPage() {
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <section className="page-content staff-page casier-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>Casier</h1>
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

      <div className="casier-empty-shell">
        <div className="casier-empty-shell-icon">
          <ShieldAlert size={20} />
        </div>
        <div>
          <strong>Aucun casier affiché pour le moment</strong>
          <p>Commence par créer un premier dossier membre depuis le bouton en haut à droite.</p>
        </div>
      </div>

      {createOpen && (
        <CreateCasierModal
          onClose={() => setCreateOpen(false)}
          onCreated={() => setCreateOpen(false)}
        />
      )}
    </section>
  );
}
