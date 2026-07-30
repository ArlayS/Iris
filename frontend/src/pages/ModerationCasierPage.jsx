import { useState } from "react";
import { Plus, Search, ShieldAlert, X } from "lucide-react";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";

export default function CasierPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [discordId, setDiscordId] = useState("");
  const [results, setResults] = useState([]);
  const [selectedMember, setSelectedMember] = useState(null);
  const [searching, setSearching] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const resetCreateState = () => {
    setQuery("");
    setDiscordId("");
    setResults([]);
    setSelectedMember(null);
    setSearching(false);
    setSubmitting(false);
  };

  const openCreateModal = () => {
    resetCreateState();
    setCreateOpen(true);
  };

  const closeCreateModal = () => {
    setCreateOpen(false);
    resetCreateState();
  };

  const searchMembers = async () => {
    const value = query.trim();
    if (!value) {
      setResults([]);
      return;
    }

    setSearching(true);
    try {
      const response = await api.get("/moderation/casiers/search-members", {
        params: { q: value },
      });
      setResults(response.data);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSearching(false);
    }
  };

  const handleSelectMember = (member) => {
    setSelectedMember(member);
    setDiscordId(member.id);
  };

  const createCasier = async () => {
    const payload = {
      member_id: selectedMember?.id || null,
      discord_id: discordId.trim() || null,
    };

    if (!payload.member_id && !payload.discord_id) {
      toast.error("Sélectionnez un membre ou entrez un ID Discord.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await api.post("/moderation/casiers", payload);
      toast.success("Casier créé.");
      closeCreateModal();
      console.log("Casier créé :", response.data);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="page-content staff-page casier-page" data-testid="casier-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>Casier</h1>
        </div>

        <div className="dashboard-actions">
          <button
            className="calm-primary-button"
            type="button"
            onClick={openCreateModal}
            data-testid="open-create-casier-button"
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
        <div className="casier-modal-backdrop" role="presentation" onClick={closeCreateModal}>
          <div
            className="casier-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-casier-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="casier-modal-header">
              <div>
                <p className="eyebrow">MODÉRATION</p>
                <h2 id="create-casier-title">Créer un casier</h2>
              </div>

              <button type="button" className="icon-button" onClick={closeCreateModal} aria-label="Fermer">
                <X size={16} />
              </button>
            </div>

            <div className="casier-modal-body">
              <div className="casier-modal-section">
                <label className="casier-label" htmlFor="casier-member-search">
                  Rechercher un membre
                </label>

                <div className="casier-search-row">
                  <div className="casier-search-input">
                    <Search size={16} />
                    <input
                      id="casier-member-search"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder="Pseudo, nom affiché ou ID"
                    />
                  </div>

                  <button
                    type="button"
                    className="calm-primary-button is-secondary"
                    onClick={searchMembers}
                    disabled={searching || !query.trim()}
                  >
                    {searching ? "Recherche…" : "Rechercher"}
                  </button>
                </div>

                <div className="casier-search-results">
                  {results.length === 0 ? (
                    <p className="resources-empty">Aucun résultat pour le moment.</p>
                  ) : (
                    results.map((member) => {
                      const isActive = selectedMember?.id === member.id;

                      return (
                        <button
                          key={member.id}
                          type="button"
                          className={`casier-search-result ${isActive ? "is-active" : ""}`}
                          onClick={() => handleSelectMember(member)}
                        >
                          <div>
                            <strong>{member.display_name || member.username}</strong>
                            <small>@{member.username}</small>
                          </div>
                          <small>{member.id}</small>
                        </button>
                      );
                    })
                  )}
                </div>
              </div>

              <div className="casier-modal-section">
                <label className="casier-label" htmlFor="casier-discord-id">
                  Ou entrer un ID Discord
                </label>
                <input
                  id="casier-discord-id"
                  className="casier-text-input"
                  value={discordId}
                  onChange={(event) => setDiscordId(event.target.value)}
                  placeholder="Ex. 918121536911732747"
                  inputMode="numeric"
                />
              </div>

              <div className="casier-modal-actions">
                <button type="button" className="calm-primary-button is-secondary" onClick={closeCreateModal}>
                  Annuler
                </button>
                <button
                  type="button"
                  className="calm-primary-button"
                  onClick={createCasier}
                  disabled={submitting}
                >
                  <Plus size={16} />
                  {submitting ? "Création…" : "Créer le casier"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
