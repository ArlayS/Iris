import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Search, UserPlus, X } from "lucide-react";
import { api, getErrorMessage } from "../api/client";

export default function AddMemberModal({ projectId, existingIds, onAdded, onClose }) {
  const [pool, setPool] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [addingId, setAddingId] = useState(null);

  useEffect(() => {
    api
      .get("/animateur/members/search")
      .then((response) => setPool(response.data))
      .catch((error) => toast.error(getErrorMessage(error)))
      .finally(() => setLoading(false));
  }, []);

  const results = useMemo(() => {
    const term = query.trim().toLowerCase();
    return pool
      .filter((member) => !existingIds.includes(member.id))
      .filter((member) => {
        if (!term) return true;
        const label = `${member.display_name || ""} ${member.username}`.toLowerCase();
        return label.includes(term);
      })
      .slice(0, 30);
  }, [pool, query, existingIds]);

  const addMember = async (member) => {
    setAddingId(member.id);
    try {
      const response = await api.post(`/animateur/projects/${projectId}/members`, {
        member_id: member.id,
        role: "membre",
      });
      onAdded(response.data);
      toast.success(`${member.display_name || member.username} ajouté au projet.`);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setAddingId(null);
    }
  };

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(28, 38, 34, 0.35)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50,
      }}
      onClick={onClose}
    >
      <div
        className="dashboard-card"
        style={{ width: "min(440px, 90vw)", maxHeight: "70vh", display: "flex", flexDirection: "column", gap: 14 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong style={{ fontSize: 16 }}>Ajouter un membre</strong>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Fermer">
            <X size={18} />
          </button>
        </div>

        <div style={{ position: "relative" }}>
          <Search size={16} style={{ position: "absolute", left: 12, top: 12, color: "var(--muted)" }} />
          <input
            className="meeting-inline-input"
            style={{ paddingLeft: 36 }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Rechercher un helper par pseudo…"
            autoFocus
          />
        </div>

        <div style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
          {loading ? (
            <p className="dashboard-loading">Chargement…</p>
          ) : results.length === 0 ? (
            <p className="resources-empty">Aucun membre trouvé.</p>
          ) : (
            results.map((member) => (
              <div
                key={member.id}
                style={{
                  display: "flex", alignItems: "center", gap: 10, padding: 8,
                  borderRadius: 8, background: "#f7faf7",
                }}
              >
                <span className="absence-avatar" style={{ width: 28, height: 28 }}>
                  {member.avatar_url ? <img src={member.avatar_url} alt="" /> : null}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <strong style={{ display: "block", fontSize: 13 }}>{member.display_name || member.username}</strong>
                  <small style={{ color: "var(--muted)" }}>@{member.username}</small>
                </div>
                <button
                  type="button"
                  className="calm-primary-button is-secondary"
                  onClick={() => addMember(member)}
                  disabled={addingId === member.id}
                >
                  <UserPlus size={14} /> {addingId === member.id ? "…" : "Ajouter"}
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
