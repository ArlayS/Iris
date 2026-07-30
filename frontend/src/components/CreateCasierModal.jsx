import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Plus, Search, X } from "lucide-react";
import { api, getErrorMessage } from "../api/client";

export default function CreateCasierModal({ onClose, onCreated }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selectedMember, setSelectedMember] = useState(null);
  const [discordId, setDiscordId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    inputRef.current?.focus();

    const onKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

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
      onCreated?.(response.data);
      toast.success("Casier créé.");
      onClose();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(28, 38, 34, 0.35)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
      }}
      onClick={onClose}
    >
      <div
        className="dashboard-card"
        style={{
          width: "min(460px, 90vw)",
          maxHeight: "72vh",
          display: "flex",
          flexDirection: "column",
          gap: 14,
        }}
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-casier-title"
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <small className="eyebrow">MODÉRATION</small>
            <strong id="create-casier-title" style={{ fontSize: 18, display: "block", marginTop: 4 }}>
              Créer un casier
            </strong>
          </div>

          <button type="button" className="icon-button" onClick={onClose} aria-label="Fermer">
            <X size={18} />
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label htmlFor="casier-member-search" style={{ fontWeight: 600 }}>
            Rechercher un membre
          </label>

          <div style={{ position: "relative" }}>
            <Search
              size={16}
              style={{
                position: "absolute",
                left: 12,
                top: 12,
                color: "var(--muted)",
              }}
            />
            <input
              ref={inputRef}
              id="casier-member-search"
              className="meeting-inline-input"
              style={{ paddingLeft: 36 }}
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

        <div style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
          {results.length === 0 ? (
            <p className="resources-empty">Aucun résultat pour le moment.</p>
          ) : (
            results.map((member) => {
              const active = selectedMember?.id === member.id;

              return (
                <button
                  key={member.id}
                  type="button"
                  onClick={() => {
                    setSelectedMember(member);
                    setDiscordId(member.id);
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 10,
                    padding: 10,
                    borderRadius: 8,
                    border: active ? "1px solid rgba(1, 105, 111, 0.24)" : "1px solid transparent",
                    background: active ? "rgba(1, 105, 111, 0.08)" : "#f7faf7",
                    textAlign: "left",
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <strong style={{ display: "block", fontSize: 13 }}>
                      {member.display_name || member.username}
                    </strong>
                    <small style={{ color: "var(--muted)" }}>@{member.username}</small>
                  </div>
                  <small style={{ color: "var(--muted)" }}>{member.id}</small>
                </button>
              );
            })
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label htmlFor="casier-discord-id" style={{ fontWeight: 600 }}>
            Ou entrer un ID Discord
          </label>
          <input
            id="casier-discord-id"
            className="meeting-inline-input"
            value={discordId}
            onChange={(event) => setDiscordId(event.target.value)}
            placeholder="Ex. 918121536911732747"
            inputMode="numeric"
          />
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button type="button" className="calm-primary-button is-secondary" onClick={onClose}>
            Annuler
          </button>
          <button
            type="button"
            className="calm-primary-button"
            onClick={createCasier}
            disabled={submitting}
          >
            <Plus size={14} /> {submitting ? "Création…" : "Créer le casier"}
          </button>
        </div>
      </div>
    </div>
  );
}
