import { useMemo, useState } from "react";
import {
  AlertTriangle,
  BadgeAlert,
  Ban,
  FileText,
  Filter,
  Gavel,
  History,
  MessageSquareWarning,
  Search,
  Shield,
  ShieldAlert,
  UserRound,
  Users,
} from "lucide-react";

const MOD_TABS = [
  { id: "reports", label: "Signalements", icon: MessageSquareWarning },
  { id: "records", label: "Casier", icon: ShieldAlert },
];

const MOCK_MEMBERS = [
  {
    id: "1",
    username: "Noctis",
    display_name: "Noctis",
    avatar_url: null,
    joined_at: "2026-02-12",
    roles: ["Membre"],
    status: "surveillance",
    summary: {
      warnings: 3,
      timeouts: 1,
      bans: 0,
      notes: 4,
      last_action_at: "2026-07-29 18:42",
    },
    notes: "Membre parfois agressif en ticket. À surveiller sur les réponses à la modération.",
    history: [
      {
        id: "h1",
        type: "warning",
        title: "Avertissement",
        reason: "Insultes légères en salon public.",
        created_at: "2026-07-29 18:42",
        created_by: "Luna",
      },
      {
        id: "h2",
        type: "timeout",
        title: "Exclusion temporaire",
        reason: "Provocation répétée malgré rappel.",
        duration: "12h",
        created_at: "2026-07-14 21:10",
        created_by: "Aster",
      },
      {
        id: "h3",
        type: "note",
        title: "Note interne",
        reason: "A reconnu les faits en ticket, profil récupérable.",
        created_at: "2026-07-14 21:32",
        created_by: "Luna",
      },
    ],
  },
  {
    id: "2",
    username: "Selene",
    display_name: "Sélène",
    avatar_url: null,
    joined_at: "2025-11-08",
    roles: ["Membre", "Création"],
    status: "clean",
    summary: {
      warnings: 0,
      timeouts: 0,
      bans: 0,
      notes: 1,
      last_action_at: "2026-06-01 10:14",
    },
    notes: "RAS. Une ancienne remontée classée sans suite.",
    history: [
      {
        id: "h4",
        type: "note",
        title: "Note interne",
        reason: "Signalement clos, aucune sanction retenue.",
        created_at: "2026-06-01 10:14",
        created_by: "Milo",
      },
    ],
  },
  {
    id: "3",
    username: "Riven",
    display_name: "Riven",
    avatar_url: null,
    joined_at: "2026-03-19",
    roles: ["Membre"],
    status: "critical",
    summary: {
      warnings: 5,
      timeouts: 2,
      bans: 1,
      notes: 6,
      last_action_at: "2026-07-30 09:05",
    },
    notes: "Cas sensible. Historique lourd, plusieurs signalements confirmés.",
    history: [
      {
        id: "h5",
        type: "ban",
        title: "Bannissement",
        reason: "Contournement de sanction + harcèlement ciblé.",
        created_at: "2026-07-30 09:05",
        created_by: "Aster",
      },
      {
        id: "h6",
        type: "warning",
        title: "Avertissement",
        reason: "Spam et provocations en vocal.",
        created_at: "2026-07-12 23:19",
        created_by: "Luna",
      },
      {
        id: "h7",
        type: "note",
        title: "Note interne",
        reason: "Conserver les transcripts et captures associées.",
        created_at: "2026-07-12 23:30",
        created_by: "Luna",
      },
    ],
  },
];

function ModerationAvatar({ member, size = 36 }) {
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

function statusLabel(status) {
  switch (status) {
    case "critical":
      return "Critique";
    case "surveillance":
      return "Surveillance";
    default:
      return "RAS";
  }
}

function historyIcon(type) {
  switch (type) {
    case "warning":
      return <AlertTriangle size={15} />;
    case "timeout":
      return <Shield size={15} />;
    case "ban":
      return <Ban size={15} />;
    case "note":
      return <FileText size={15} />;
    default:
      return <History size={15} />;
  }
}

export default function ModerationPage() {
  const [activeTab, setActiveTab] = useState("records");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectedMemberId, setSelectedMemberId] = useState(MOCK_MEMBERS[0]?.id ?? null);
  const [newActionType, setNewActionType] = useState("warning");
  const [newActionReason, setNewActionReason] = useState("");

  const filteredMembers = useMemo(() => {
    return MOCK_MEMBERS.filter((member) => {
      const needle = query.trim().toLowerCase();
      const matchesQuery =
        !needle ||
        member.username.toLowerCase().includes(needle) ||
        member.display_name.toLowerCase().includes(needle);

      const matchesStatus = statusFilter === "all" || member.status === statusFilter;
      return matchesQuery && matchesStatus;
    });
  }, [query, statusFilter]);

  const selectedMember =
    filteredMembers.find((member) => member.id === selectedMemberId) ||
    filteredMembers[0] ||
    null;

  return (
    <section className="page-content staff-page moderation-page" data-testid="moderation-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>Modération</h1>
        </div>

        <div className="dashboard-actions">
          <button className="calm-primary-button is-secondary" type="button">
            <MessageSquareWarning size={17} />
            Voir les signalements
          </button>
          <button className="calm-primary-button" type="button">
            <Gavel size={17} />
            Nouvelle action
          </button>
        </div>
      </header>

      <div className="moderation-tabs" role="tablist" aria-label="Navigation modération">
        {MOD_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = tab.id === activeTab;

          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={`moderation-tab ${isActive ? "is-active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {activeTab === "reports" ? (
        <div className="moderation-placeholder-card">
          <div className="moderation-placeholder-icon">
            <MessageSquareWarning size={20} />
          </div>
          <div>
            <strong>Signalements</strong>
            <p>Prévois ici la file de signalements, la priorisation et les décisions de traitement.</p>
          </div>
        </div>
      ) : (
        <div className="moderation-layout">
          <aside className="moderation-sidebar">
            <div className="moderation-card moderation-search-card">
              <div className="moderation-field">
                <label htmlFor="moderation-search">Recherche</label>
                <div className="moderation-input-wrap">
                  <Search size={16} />
                  <input
                    id="moderation-search"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Pseudo ou nom affiché"
                  />
                </div>
              </div>

              <div className="moderation-field">
                <label htmlFor="moderation-filter">Statut</label>
                <div className="moderation-input-wrap is-select">
                  <Filter size={16} />
                  <select
                    id="moderation-filter"
                    value={statusFilter}
                    onChange={(event) => setStatusFilter(event.target.value)}
                  >
                    <option value="all">Tous</option>
                    <option value="clean">RAS</option>
                    <option value="surveillance">Surveillance</option>
                    <option value="critical">Critique</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="moderation-card moderation-stats-card">
              <div className="moderation-stat">
                <small>Membres suivis</small>
                <strong>{MOCK_MEMBERS.length}</strong>
              </div>
              <div className="moderation-stat">
                <small>Critiques</small>
                <strong>{MOCK_MEMBERS.filter((m) => m.status === "critical").length}</strong>
              </div>
              <div className="moderation-stat">
                <small>Sous surveillance</small>
                <strong>{MOCK_MEMBERS.filter((m) => m.status === "surveillance").length}</strong>
              </div>
            </div>
          </aside>

          <div className="moderation-members-column">
            <div className="moderation-card moderation-column-header">
              <div>
                <p className="eyebrow">CASIERS</p>
                <strong>Liste des membres</strong>
              </div>
              <span className="moderation-count">{filteredMembers.length}</span>
            </div>

            <div className="moderation-member-list">
              {filteredMembers.length === 0 ? (
                <div className="moderation-card moderation-empty-state">
                  <Users size={18} />
                  <p>Aucun membre ne correspond aux filtres actuels.</p>
                </div>
              ) : (
                filteredMembers.map((member) => {
                  const isSelected = selectedMember?.id === member.id;

                  return (
                    <button
                      key={member.id}
                      type="button"
                      className={`moderation-member-row ${isSelected ? "is-selected" : ""}`}
                      onClick={() => setSelectedMemberId(member.id)}
                    >
                      <ModerationAvatar member={member} size={42} />

                      <div className="moderation-member-copy">
                        <div className="moderation-member-heading">
                          <strong>{member.display_name}</strong>
                          <span className={`moderation-status-badge is-${member.status}`}>
                            {statusLabel(member.status)}
                          </span>
                        </div>

                        <small>@{member.username}</small>

                        <div className="moderation-member-meta">
                          <span>{member.summary.warnings} avert.</span>
                          <span>{member.summary.timeouts} timeout</span>
                          <span>{member.summary.bans} ban</span>
                        </div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          <div className="moderation-detail-column">
            {!selectedMember ? (
              <div className="moderation-card moderation-empty-state">
                <ShieldAlert size={18} />
                <p>Sélectionne un membre pour ouvrir son casier.</p>
              </div>
            ) : (
              <>
                <div className="moderation-card moderation-record-header">
                  <div className="moderation-record-identity">
                    <ModerationAvatar member={selectedMember} size={54} />
                    <div>
                      <h2>{selectedMember.display_name}</h2>
                      <small>@{selectedMember.username}</small>

                      <div className="moderation-role-list">
                        {selectedMember.roles.map((role) => (
                          <span key={role} className="moderation-role-chip">
                            {role}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="moderation-record-summary">
                    <div>
                      <small>Avertissements</small>
                      <strong>{selectedMember.summary.warnings}</strong>
                    </div>
                    <div>
                      <small>Timeouts</small>
                      <strong>{selectedMember.summary.timeouts}</strong>
                    </div>
                    <div>
                      <small>Bans</small>
                      <strong>{selectedMember.summary.bans}</strong>
                    </div>
                    <div>
                      <small>Dernière action</small>
                      <strong>{selectedMember.summary.last_action_at}</strong>
                    </div>
                  </div>
                </div>

                <div className="moderation-detail-grid">
                  <section className="moderation-card moderation-panel">
                    <div className="moderation-panel-header">
                      <BadgeAlert size={16} />
                      <strong>Résumé du casier</strong>
                    </div>

                    <p className="moderation-note-text">{selectedMember.notes}</p>

                    <ul className="moderation-summary-list">
                      <li>Membre arrivé le {selectedMember.joined_at}</li>
                      <li>Statut actuel : {statusLabel(selectedMember.status)}</li>
                      <li>{selectedMember.history.length} entrée(s) dans l’historique</li>
                    </ul>
                  </section>

                  <section className="moderation-card moderation-panel">
                    <div className="moderation-panel-header">
                      <Gavel size={16} />
                      <strong>Ajouter une action</strong>
                    </div>

                    <div className="moderation-field">
                      <label htmlFor="action-type">Type</label>
                      <select
                        id="action-type"
                        value={newActionType}
                        onChange={(event) => setNewActionType(event.target.value)}
                      >
                        <option value="warning">Avertissement</option>
                        <option value="timeout">Exclusion temporaire</option>
                        <option value="ban">Bannissement</option>
                        <option value="note">Note interne</option>
                      </select>
                    </div>

                    <div className="moderation-field">
                      <label htmlFor="action-reason">Motif</label>
                      <textarea
                        id="action-reason"
                        rows={5}
                        value={newActionReason}
                        onChange={(event) => setNewActionReason(event.target.value)}
                        placeholder="Décris précisément les faits, le contexte et la raison de l’action."
                      />
                    </div>

                    <div className="moderation-inline-actions">
                      <button className="calm-primary-button" type="button">
                        <Gavel size={16} />
                        Enregistrer
                      </button>
                      <button className="calm-primary-button is-secondary" type="button">
                        <FileText size={16} />
                        Ajouter une note
                      </button>
                    </div>
                  </section>

                  <section className="moderation-card moderation-panel moderation-history-panel">
                    <div className="moderation-panel-header">
                      <History size={16} />
                      <strong>Historique</strong>
                    </div>

                    <div className="moderation-timeline">
                      {selectedMember.history.map((entry) => (
                        <article key={entry.id} className="moderation-timeline-item">
                          <span className={`moderation-timeline-icon is-${entry.type}`}>
                            {historyIcon(entry.type)}
                          </span>

                          <div className="moderation-timeline-body">
                            <div className="moderation-timeline-head">
                              <strong>{entry.title}</strong>
                              <small>{entry.created_at}</small>
                            </div>

                            <p>{entry.reason}</p>

                            <small>
                              Par {entry.created_by}
                              {entry.duration ? ` · Durée ${entry.duration}` : ""}
                            </small>
                          </div>
                        </article>
                      ))}
                    </div>
                  </section>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
