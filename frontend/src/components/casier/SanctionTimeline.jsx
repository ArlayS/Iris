import "./casier-detail.css";

import { useEffect, useMemo, useRef, useState } from "react";
import { History, Plus } from "lucide-react";

import SanctionCard from "./SanctionCard";
import { REMINDER_TYPE, TIMELINE_FILTERS, sanctionTypeMeta } from "./casierConstants";

function matchesFilter(sanction, filter) {
  if (filter === "sanctions") return sanction.type !== REMINDER_TYPE;
  if (filter === "rappels") return sanction.type === REMINDER_TYPE;
  return true;
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

const EMPTY_FILTER_MESSAGES = {
  sanctions: "Aucune sanction hors rappels à l'ordre.",
  rappels: "Aucun rappel à l'ordre.",
};

// Onglet « Historique » : sanctions et rappels, du plus récent au plus ancien (ordre de l'API).
export default function SanctionTimeline({
  casier,
  highlightSanctionId = null,
  onAddSanction,
  onFilesQueued,
  copyStalled = false,
}) {
  const [filter, setFilter] = useState("tout");
  const filterHandledRef = useRef(null);
  const scrolledRef = useRef(null);

  const sanctions = useMemo(() => (Array.isArray(casier?.sanctions) ? casier.sanctions : []), [casier?.sanctions]);
  const counts = useMemo(
    () => ({
      tout: sanctions.length,
      sanctions: sanctions.filter((item) => item.type !== REMINDER_TYPE).length,
      rappels: sanctions.filter((item) => item.type === REMINDER_TYPE).length,
    }),
    [sanctions]
  );
  const visible = useMemo(() => sanctions.filter((item) => matchesFilter(item, filter)), [sanctions, filter]);

  // Sanction ciblée masquée par le filtre : on revient à « Tout » (une fois par cible).
  useEffect(() => {
    if (!highlightSanctionId || filterHandledRef.current === highlightSanctionId) return;
    const target = sanctions.find((item) => item.id === highlightSanctionId);
    if (!target) return;
    filterHandledRef.current = highlightSanctionId;
    if (!matchesFilter(target, filter)) setFilter("tout");
  }, [highlightSanctionId, sanctions, filter]);

  // Défilement vers la carte ciblée, une seule fois par cible, dès qu'elle est rendue.
  useEffect(() => {
    if (!highlightSanctionId || scrolledRef.current === highlightSanctionId) return;
    const node = document.getElementById(`sanction-${highlightSanctionId}`);
    if (!node) return;
    scrolledRef.current = highlightSanctionId;
    node.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [highlightSanctionId, visible]);

  if (sanctions.length === 0) {
    return (
      <div className="cz-card cz-empty">
        <History size={26} aria-hidden="true" />
        <h3>Aucune sanction enregistrée pour ce membre.</h3>
        <p>Les sanctions publiées par OasisBot s'ajoutent toutes seules. Vous pouvez aussi en ajouter une à la main.</p>
        <div className="cz-empty-actions">
          <button type="button" className="cz-button cz-button--primary" onClick={onAddSanction}>
            <Plus size={16} aria-hidden="true" />
            Ajouter une sanction
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="cz-timeline">
      <div className="cz-timeline-toolbar">
        <div className="cz-chips" role="group" aria-label="Filtrer l'historique">
          {TIMELINE_FILTERS.map((option) => (
            <button
              key={option.value}
              type="button"
              className="cz-chip"
              aria-pressed={filter === option.value}
              onClick={() => setFilter(option.value)}
            >
              {option.label}
              <span className="cz-chip-count">{counts[option.value] ?? 0}</span>
            </button>
          ))}
        </div>
      </div>

      {visible.length === 0 ? (
        <div className="cz-card cz-empty cz-empty--compact">
          <p>{EMPTY_FILTER_MESSAGES[filter] || "Aucun élément pour ce filtre."}</p>
          <div className="cz-empty-actions">
            <button type="button" className="cz-button cz-button--compact" onClick={() => setFilter("tout")}>
              Tout afficher
            </button>
          </div>
        </div>
      ) : (
        <ol className="cz-timeline-list" aria-label="Historique des sanctions">
          {visible.map((sanction) => (
            <li
              key={sanction.id || `${sanction.type}-${sanction.created_at}`}
              className={`cz-timeline-item cz-timeline-item--${sanctionTypeMeta(sanction.type).tone}`}
            >
              <SanctionCard
                casierId={casier.id}
                sanction={sanction}
                highlighted={Boolean(highlightSanctionId) && sanction.id === highlightSanctionId}
                onFilesQueued={onFilesQueued}
                copyStalled={copyStalled}
              />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
