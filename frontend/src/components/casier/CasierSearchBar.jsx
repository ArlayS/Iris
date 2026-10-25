import "./casier-list.css";

import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, Loader2, RotateCcw, Search, SlidersHorizontal, X } from "lucide-react";

import {
  CASIER_TOGGLE_FILTERS,
  DEFAULT_SORT,
  SEARCH_MAX_LENGTH,
  SEARCH_SCOPES,
  SORT_OPTIONS,
  STATUS_FILTERS,
} from "./casierConstants";

const EDITABLE_TARGET = 'input, textarea, select, [contenteditable]:not([contenteditable="false"])';
const OPEN_DIALOG = '[role="dialog"], [role="alertdialog"]';

function isEditableTarget(target) {
  if (!target || typeof target.closest !== "function") return false;
  return Boolean(target.isContentEditable || target.closest(EDITABLE_TARGET));
}

function countActive(filters) {
  const statuses = Array.isArray(filters?.status) ? filters.status.length : 0;
  const toggles = CASIER_TOGGLE_FILTERS.filter((option) => Boolean(filters?.[option.key])).length;
  const sort = filters?.sort && filters.sort !== DEFAULT_SORT ? 1 : 0;
  return statuses + toggles + sort;
}

// Champ contrôlé : chaque frappe remonte telle quelle, l'anti-rebond est fait par la page.
export default function CasierSearchBar({
  filters,
  onChange,
  onReset,
  canReset = false,
  notice = null,
  busy = false,
}) {
  const inputRef = useRef(null);
  const [focused, setFocused] = useState(false);
  const activeCount = countActive(filters);
  // Statuts, bascules et tri dans un volet : la liste garde la hauteur utile du panneau.
  const [filtersOpen, setFiltersOpen] = useState(() => activeCount > 0);
  const baseId = useId();
  const noticeId = `${baseId}-notice`;
  const sortId = `${baseId}-sort`;
  const panelId = `${baseId}-filters`;

  const q = typeof filters?.q === "string" ? filters.q : "";
  const scope = filters?.scope;
  const statuses = Array.isArray(filters?.status) ? filters.status : [];
  const sort = filters?.sort;

  // Raccourci « / » : place le focus dans le champ quand rien d'autre n'attend la frappe.
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key !== "/" || event.defaultPrevented || event.isComposing) return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (isEditableTarget(event.target)) return;
      if (document.querySelector(OPEN_DIALOG)) return;
      const input = inputRef.current;
      if (!input || input.offsetParent === null) return;
      event.preventDefault();
      input.focus();
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const clearQuery = () => {
    onChange?.({ q: "" });
    inputRef.current?.focus();
  };

  const handleInputKeyDown = (event) => {
    if (event.key === "Escape" && q) {
      event.preventDefault();
      event.stopPropagation();
      clearQuery();
    }
  };

  const toggleStatus = (value) => {
    const next = statuses.includes(value)
      ? statuses.filter((item) => item !== value)
      : [...statuses, value];
    onChange?.({ status: next });
  };

  return (
    <div className="cz-searchbar">
      <div className="cz-searchbar-query">
        <label className="cz-search cz-searchbar-field">
          <Search size={18} aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            value={q}
            onChange={(event) => onChange?.({ q: event.target.value })}
            onKeyDown={handleInputKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder="Rechercher un membre, un modérateur, un motif…"
            aria-label="Rechercher dans les casiers"
            aria-describedby={notice ? noticeId : undefined}
            aria-keyshortcuts="/"
            maxLength={SEARCH_MAX_LENGTH}
            autoComplete="off"
            enterKeyHint="search"
            spellCheck={false}
          />

          {busy && <Loader2 size={16} className="cz-spin cz-searchbar-busy" aria-hidden="true" />}

          {q ? (
            <button
              type="button"
              className="cz-search-clear"
              onClick={clearQuery}
              aria-label="Effacer la recherche"
            >
              <X size={16} aria-hidden="true" />
            </button>
          ) : (
            !focused && (
              <kbd className="cz-kbd cz-searchbar-kbd" title="Appuyez sur / pour rechercher" aria-hidden="true">
                /
              </kbd>
            )
          )}
        </label>

        <p id={noticeId} className="cz-hint cz-searchbar-notice" role="status">
          {notice || ""}
        </p>
      </div>

      <div className="cz-searchbar-scope">
        <span className="cz-searchbar-label" aria-hidden="true">
          Dans
        </span>
        <div className="cz-chips" role="group" aria-label="Portée de la recherche">
          {SEARCH_SCOPES.map((option) => {
            const active = scope === option.value;
            return (
              <button
                key={option.value}
                type="button"
                className="cz-chip"
                aria-pressed={active}
                onClick={() => {
                  if (!active) onChange?.({ scope: option.value });
                }}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="cz-searchbar-actions">
        <button
          type="button"
          className="cz-chip cz-searchbar-toggle"
          aria-expanded={filtersOpen}
          aria-controls={panelId}
          onClick={() => setFiltersOpen((open) => !open)}
        >
          <SlidersHorizontal size={14} aria-hidden="true" />
          Filtres et tri
          {activeCount > 0 && (
            <span className="cz-searchbar-badge">
              {activeCount}
              <span className="cz-sr-only">{activeCount > 1 ? " actifs" : " actif"}</span>
            </span>
          )}
          <ChevronDown size={14} className="cz-searchbar-chevron" aria-hidden="true" />
        </button>

        {canReset && (
          <button type="button" className="cz-chip cz-chip--reset" onClick={() => onReset?.()}>
            <RotateCcw size={14} aria-hidden="true" />
            Réinitialiser
          </button>
        )}
      </div>

      <div id={panelId} className="cz-searchbar-filters" hidden={!filtersOpen}>
        <div className="cz-chips" role="group" aria-label="Statut">
          {STATUS_FILTERS.map((option) => {
            const active = statuses.includes(option.value);
            return (
              <button
                key={option.value}
                type="button"
                className="cz-chip"
                aria-pressed={active}
                onClick={() => toggleStatus(option.value)}
              >
                <span className={`cz-searchbar-dot cz-searchbar-dot--${option.tone}`} aria-hidden="true" />
                {option.label}
              </button>
            );
          })}
        </div>

        <div className="cz-chips" role="group" aria-label="Filtres">
          {CASIER_TOGGLE_FILTERS.map((option) => {
            const active = Boolean(filters?.[option.key]);
            return (
              <button
                key={option.key}
                type="button"
                className="cz-chip"
                aria-pressed={active}
                onClick={() => onChange?.({ [option.key]: !active })}
              >
                {option.label}
              </button>
            );
          })}
        </div>

        <div className="cz-searchbar-sort">
          <label htmlFor={sortId} className="cz-searchbar-label">
            Trier par
          </label>
          <select
            id={sortId}
            className="cz-select cz-searchbar-select"
            value={sort}
            onChange={(event) => onChange?.({ sort: event.target.value })}
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
