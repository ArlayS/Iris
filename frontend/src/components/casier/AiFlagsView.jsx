import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Bot, Loader2, Search, X } from "lucide-react";

import "./casier-fiches-ia.css";
import AiFlagList, { useAiFlagPages } from "./AiFlagList";
import {
  AI_CATEGORY_OPTIONS,
  DEFAULT_REVIEW_FILTER,
  GRAVITY_FILTERS,
  KIND_FILTERS,
  REVIEW_FILTERS,
  SEARCH_DEBOUNCE_MS,
  SEARCH_MAX_LENGTH,
} from "./casierConstants";
import { plural } from "./formatters";

const DEFAULT_FILTERS = {
  q: "",
  review_status: DEFAULT_REVIEW_FILTER,
  min_gravity: null,
  category: "",
  kind: "",
};

function useDebouncedValue(value, delay) {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}

// Vue « Signalements IA » : panneau pleine largeur, filtres propres, liste paginée.
export default function AiFlagsView({ highlightFlagId = null, onNavigate }) {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const inputRef = useRef(null);
  const ids = useId();
  const categoryId = `${ids}-categorie`;
  const kindId = `${ids}-type`;

  const typed = filters.q.trim().slice(0, SEARCH_MAX_LENGTH);
  const debounced = useDebouncedValue(typed, SEARCH_DEBOUNCE_MS);
  // Effacer agit tout de suite ; la saisie attend l'anti-rebond.
  const searchQuery = typed ? debounced : "";

  const params = useMemo(() => {
    const next = { review_status: filters.review_status };
    if (searchQuery) next.q = searchQuery;
    if (filters.min_gravity) next.min_gravity = filters.min_gravity;
    if (filters.category) next.category = filters.category;
    if (filters.kind) next.kind = filters.kind;
    return next;
  }, [searchQuery, filters.review_status, filters.min_gravity, filters.category, filters.kind]);

  // Même requête que la liste (clé partagée) : compteurs des puces et total de l'en-tête.
  const query = useAiFlagPages(params);
  const firstPage = query.data?.pages?.[0];
  const counts = firstPage?.counts || null;
  const totalLabel = counts ? plural(counts.total, "signalement") : "";

  const change = (patch) => setFilters((current) => ({ ...current, ...patch }));

  const canReset =
    Boolean(filters.q) ||
    filters.review_status !== DEFAULT_FILTERS.review_status ||
    Boolean(filters.min_gravity) ||
    Boolean(filters.category) ||
    Boolean(filters.kind);

  const clearSearch = () => {
    change({ q: "" });
    inputRef.current?.focus();
  };

  const isFiltered = Boolean(searchQuery || filters.min_gravity || filters.category || filters.kind);
  const emptyMessage =
    !isFiltered && filters.review_status === "a_traiter"
      ? "Aucun signalement à traiter."
      : "Aucun signalement pour ces filtres.";

  return (
    <section className="cz-panel cz-flags-panel" aria-labelledby={`${ids}-titre`}>
      <header className="cz-panel-header cz-panel-header--blue">
        <span className="cz-panel-icon" aria-hidden="true">
          <Bot size={23} />
        </span>
        <div className="cz-panel-heading">
          <h2 id={`${ids}-titre`}>Signalements de l'automodération</h2>
          <p>Messages signalés par SecuModIA, conservés pour le suivi et la revue.</p>
        </div>
        <span className="cz-count-live" role="status" aria-live="polite">
          {totalLabel && <span className="cz-count">{totalLabel}</span>}
        </span>
      </header>

      <div className="cz-panel-toolbar cz-flags-toolbar">
        <div className="cz-search cz-flags-search">
          <Search size={17} aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            value={filters.q}
            onChange={(event) => change({ q: event.target.value })}
            onKeyDown={(event) => {
              if (event.key === "Escape" && filters.q) {
                event.preventDefault();
                clearSearch();
              }
            }}
            placeholder="Membre, message ou raison…"
            aria-label="Rechercher dans les signalements"
            maxLength={SEARCH_MAX_LENGTH}
            autoComplete="off"
            enterKeyHint="search"
          />
          {typed && query.isFetching && (
            <Loader2 size={16} className="cz-spin cz-flags-search-busy" aria-hidden="true" />
          )}
          {filters.q && (
            <button type="button" className="cz-search-clear" onClick={clearSearch} aria-label="Effacer la recherche">
              <X size={16} aria-hidden="true" />
            </button>
          )}
        </div>

        <div className="cz-flags-filters">
          <div className="cz-flags-group">
            <span className="cz-flags-group-label" id={`${ids}-revue`}>
              Revue
            </span>
            <div className="cz-chips" role="group" aria-labelledby={`${ids}-revue`}>
              {REVIEW_FILTERS.map((item) => {
                const count = counts ? counts[item.countKey] : null;
                return (
                  <button
                    key={item.value}
                    type="button"
                    className="cz-chip"
                    aria-pressed={filters.review_status === item.value}
                    onClick={() => change({ review_status: item.value })}
                  >
                    {item.label}
                    {count !== null && count !== undefined && <span className="cz-chip-count">({count})</span>}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="cz-flags-group">
            <span className="cz-flags-group-label" id={`${ids}-gravite`}>
              Gravité min.
            </span>
            <div className="cz-chips" role="group" aria-labelledby={`${ids}-gravite`}>
              {GRAVITY_FILTERS.map((item) => (
                <button
                  key={item.label}
                  type="button"
                  className="cz-chip"
                  aria-pressed={(filters.min_gravity ?? null) === item.value}
                  onClick={() => change({ min_gravity: item.value })}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="cz-flags-selects">
            <label className="cz-sr-only" htmlFor={categoryId}>
              Catégorie
            </label>
            <select
              id={categoryId}
              className="cz-select"
              value={filters.category}
              onChange={(event) => change({ category: event.target.value })}
            >
              <option value="">Toutes les catégories</option>
              {AI_CATEGORY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>

            <label className="cz-sr-only" htmlFor={kindId}>
              Type de signalement
            </label>
            <select
              id={kindId}
              className="cz-select"
              value={filters.kind}
              onChange={(event) => change({ kind: event.target.value })}
            >
              {KIND_FILTERS.map((option) => (
                <option key={option.value || "tous"} value={option.value}>
                  {option.value ? option.label : "Tous les types"}
                </option>
              ))}
            </select>

            {canReset && (
              <button type="button" className="cz-chip cz-chip--reset" onClick={() => setFilters(DEFAULT_FILTERS)}>
                Réinitialiser
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="cz-panel-body cz-flags-body">
        <AiFlagList
          params={params}
          highlightFlagId={highlightFlagId}
          onNavigate={onNavigate}
          emptyMessage={emptyMessage}
        />
      </div>
    </section>
  );
}
