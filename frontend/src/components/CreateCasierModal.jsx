import { useEffect, useRef, useState } from "react";
import { Search, ShieldAlert, UserRound, X } from "lucide-react";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";

function MemberAvatar({ member, size = 34 }) {
  const label = member?.display_name || member?.username || "?";

  return (
    <span
      className="moderation-avatar"
      style={{ width: size, height: size }}
      title={label}
      aria-label={label}
    >
      {member?.avatar_url ? (
        <img src={member.avatar_url} alt="" />
      ) : (
        <UserRound size={Math.round(size * 0.52)} />
      )}
    </span>
  );
}

export default function CreateCasierModal({
  open,
  onClose,
  onCreated,
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selectedMember, setSelectedMember] = useState(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const debounceRef = useRef(null);
  const requestIdRef = useRef(0);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!open) return;

    setQuery("");
    setResults([]);
    setSelectedMember(null);
    setLoading(false);
    setSubmitting(false);

    const timer = setTimeout(() => {
      inputRef.current?.focus();
    }, 10);

    return () => clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const needle = query.trim();

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    if (needle.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      const requestId = ++requestIdRef.current;
      setLoading(true);

      try {
        const response = await api.get("/moderation/casiers/search-members", {
          params: { q: needle },
        });

        if (requestId !== requestIdRef.current) return;

        setResults(Array.isArray(response.data) ? response.data : []);
      } catch (error) {
        if (requestId === requestIdRef.current) {
          setResults([]);
          toast.error(getErrorMessage(error));
        }
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false);
        }
      }
    }, 300);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [query, open]);

  const handleClose = () => {
    if (submitting) return;
    onClose?.();
  };

  const handlePickMember = (member) => {
    setSelectedMember(member);
    setQuery(member.display_name || member.username || "");
    setResults([]);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!selectedMember?.id) {
      toast.error("Sélectionne un membre Discord.");
      return;
    }

    setSubmitting(true);

    try {
      const response = await api.post("/moderation/casiers", {
        discord_id: selectedMember.id,
      });

      toast.success("Casier créé.");
      onCreated?.(response.data);
      onClose?.();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="modal-backdrop" role="presentation" onClick={handleClose}>
      <div
        className="modal-panel moderation-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-casier-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="moderation-modal-header">
          <div>
            <p className="eyebrow">MODÉRATION</p>
            <h2 id="create-casier-title">Créer un casier</h2>
          </div>

          <button
            type="button"
            className="icon-button"
            onClick={handleClose}
            aria-label="Fermer"
          >
            <X size={16} />
          </button>
        </div>

        <form className="moderation-modal-body" onSubmit={handleSubmit}>
          <div className="moderation-field">
            <label htmlFor="discord-member-search">Membre Discord</label>

            <div className="moderation-input-wrap">
              <Search size={16} />
              <input
                ref={inputRef}
                id="discord-member-search"
                type="text"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setSelectedMember(null);
                }}
                placeholder="Chercher un pseudo ou un nickname"
                autoComplete="off"
              />
            </div>

            <small className="moderation-help-text">
              Recherche directe parmi les membres du serveur Discord.
            </small>
          </div>

          {selectedMember && (
            <div className="moderation-selected-member">
              <MemberAvatar member={selectedMember} size={40} />
              <div>
                <strong>{selectedMember.display_name || selectedMember.username}</strong>
                <small>@{selectedMember.username}</small>
              </div>
            </div>
          )}

          {!selectedMember && query.trim().length >= 2 && (
            <div className="moderation-search-results">
              {loading ? (
                <p className="resources-empty">Recherche…</p>
              ) : results.length === 0 ? (
                <p className="resources-empty">Aucun membre trouvé.</p>
              ) : (
                results.map((member) => (
                  <button
                    key={member.id}
                    type="button"
                    className="moderation-search-result"
                    onClick={() => handlePickMember(member)}
                  >
                    <MemberAvatar member={member} size={38} />
                    <div className="moderation-search-result-copy">
                      <strong>{member.display_name || member.username}</strong>
                      <small>@{member.username}</small>
                    </div>
                  </button>
                ))
              )}
            </div>
          )}

          <div className="moderation-modal-actions">
            <button
              className="calm-primary-button is-secondary"
              type="button"
              onClick={handleClose}
              disabled={submitting}
            >
              Annuler
            </button>

            <button
              className="calm-primary-button"
              type="submit"
              disabled={!selectedMember || submitting}
            >
              <ShieldAlert size={16} />
              {submitting ? "Création…" : "Créer le casier"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
