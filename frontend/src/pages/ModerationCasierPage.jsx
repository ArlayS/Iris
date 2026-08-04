import { useEffect, useMemo, useRef, useState } from "react";
import { Plus, Search, Shield, ShieldCheck, ShieldAlert, X } from "lucide-react";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";

function MemberAvatar({ member, size = 34 }) {
  const label = member?.display_name || member?.username || "?";

  return (
    <span className="moderation-avatar" style={{ width: size, height: size }} title={label} aria-label={label}>
      {member?.avatar_url ? <img src={member.avatar_url} alt="" /> : <Shield size={Math.round(size * 0.52)} />}
    </span>
  );
}

function CasierCard({ member, selected, onClick }) {
  return (
    <button type="button" className={`casier-card ${selected ? "is-selected" : ""}`} onClick={() => onClick(member)}>
      <div className="casier-card-visual">
        <MemberAvatar member={member} size={118} />
      </div>
      <div className="casier-card-copy">
        <strong>{member.display_name || member.username}</strong>
        <span>@{member.username}</span>
      </div>
    </button>
  );
}

export default function ModerationCasierPage() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selectedMember, setSelectedMember] = useState(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [casiers, setCasiers] = useState([]);

  const inputRef = useRef(null);
  const debounceRef = useRef(null);
  const requestIdRef = useRef(0);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!open) return;

    setQuery("");
    setResults([]);
    setSelectedMember(null);
    setLoading(false);
    setSubmitting(false);

    const timer = setTimeout(() => inputRef.current?.focus(), 0);
    return () => clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const needle = query.trim();

    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (needle.length < 2 || selectedMember) {
      setLoading(false);
      if (needle.length < 2) setResults([]);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      const requestId = ++requestIdRef.current;
      setLoading(true);

      try {
        const response = await api.get("/moderation/casiers/search-members", { params: { q: needle } });
        if (!aliveRef.current || requestId !== requestIdRef.current) return;
        setResults(Array.isArray(response?.data) ? response.data : []);
      } catch (error) {
        if (!aliveRef.current || requestId !== requestIdRef.current) return;
        setResults([]);
        toast.error(getErrorMessage(error));
      } finally {
        if (aliveRef.current && requestId === requestIdRef.current) setLoading(false);
      }
    }, 250);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, open, selectedMember]);

  const latest = casiers[0];
  const canCreate = Boolean(selectedMember?.id) && !submitting;

  const handlePickMember = (member) => {
    if (!member?.id) return;
    setSelectedMember(member);
    setQuery(member.display_name || member.username || "");
    setResults([]);
  };

  const handleSubmit = async () => {
    if (!selectedMember?.id) {
      toast.error("Sélectionne un membre dans la liste.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await api.post("/moderation/casiers", { discord_id: selectedMember.id });
      if (response?.data) setCasiers((current) => [response.data, ...current]);
      toast.success("Casier créé.");
      setOpen(false);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="page-content staff-page moderation-page casier-page" data-testid="moderation-casier-page">
      <header className="page-header casier-hero">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>Modération – Casier</h1>
        </div>
      </header>

      <div className="casier-content-shell">
        <div className="casier-intro">
          <div className="casier-intro-mark">
            <Plus size={18} />
          </div>
          <div>
            <strong>Contenu à venir</strong>
            <p>Liste des casiers, filtres, et détail à implémenter ici.</p>
            <small>MODÉRATION</small>
          </div>
        </div>

        <div className="casier-toolbar">
          <button className="calm-primary-button" type="button" onClick={() => setOpen(true)}>
            <ShieldCheck size={17} />
            Créer un casier
          </button>
        </div>

        {latest && (
          <article className="casier-spotlight">
            <MemberAvatar member={latest.member} size={88} />
            <div>
              <strong>{latest.member?.display_name || latest.member?.username}</strong>
              <p>{latest.last_entry_label || "Dossier créé."}</p>
            </div>
          </article>
        )}
      </div>

      {open && (
        <div className="casier-modal-backdrop" role="presentation" onClick={() => setOpen(false)}>
          <div className="casier-modal" role="dialog" aria-modal="true" aria-labelledby="casier-modal-title" onClick={(event) => event.stopPropagation()}>
            <div className="casier-modal-header">
              <div>
                <p className="eyebrow">MODÉRATION</p>
                <h2 id="casier-modal-title">Créer un casier</h2>
              </div>
              <button type="button" className="icon-button" onClick={() => setOpen(false)} aria-label="Fermer">
                <X size={16} />
              </button>
            </div>

            <div className="casier-modal-body">
              <div className="moderation-field">
                <label htmlFor="discord-member-search">Membre Discord</label>
                <div className="casier-search-wrap">
                  <Search size={16} />
                  <input
                    ref={inputRef}
                    id="discord-member-search"
                    value={query}
                    onChange={(event) => {
                      const value = event.target.value;
                      setQuery(value);
                      if (selectedMember && value !== (selectedMember.display_name || selectedMember.username || "")) {
                        setSelectedMember(null);
                      }
                    }}
                    placeholder="tho"
                    autoComplete="off"
                  />
                </div>
                <small>Tape au moins 2 caractères puis choisis un membre dans la liste.</small>
              </div>

              {!selectedMember && query.trim().length >= 2 && (
                <div className="casier-results-grid">
                  {loading ? (
                    <p className="resources-empty">Recherche…</p>
                  ) : results.length === 0 ? (
                    <p className="resources-empty">Aucun membre trouvé.</p>
                  ) : (
                    results.map((member) => <CasierCard key={member.id} member={member} selected={false} onClick={handlePickMember} />)
                  )}
                </div>
              )}

              {selectedMember && (
                <div className="casier-selection-row">
                  <MemberAvatar member={selectedMember} size={42} />
                  <div>
                    <strong>{selectedMember.display_name || selectedMember.username}</strong>
                    <small>@{selectedMember.username}</small>
                  </div>
                </div>
              )}

              <div className="casier-actions">
                <button type="button" className="calm-primary-button is-secondary" onClick={() => setOpen(false)}>
                  Annuler
                </button>
                <button type="button" className="calm-primary-button" onClick={handleSubmit} disabled={!canCreate}>
                  <ShieldAlert size={16} />
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
