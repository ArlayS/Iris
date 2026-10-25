import "./casier/casier-list.css";

import { useEffect, useId, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useQueryClient } from "@tanstack/react-query";
import { CircleAlert, Info, Loader2, Search, ShieldCheck, UserRoundSearch, UserX, X } from "lucide-react";
import { toast } from "sonner";

import MemberAvatar from "./casier/MemberAvatar";
import {
  casierKeys,
  createCasier,
  errorMessage,
  findCasierByDiscordId,
  getCasier,
  isApiError,
  searchMembers,
} from "./casier/casierApi";
import { MEMBER_SEARCH_DEBOUNCE_MS, MEMBER_SEARCH_MIN_LENGTH } from "./casier/casierConstants";
import { memberHandle, memberName } from "./casier/formatters";

const DISCORD_ID_PATTERN = /^\d{17,20}$/;
const DISCORD_ID_MAX_LENGTH = 20;
const USERNAME_MAX_LENGTH = 80;
const MODE_MEMBER = "membre";
const MODE_PREVENTION = "prevention";
const EMPTY_SEARCH = { term: "", results: [], error: null };

function memberUsername(member) {
  return String(member?.display_name || member?.username || "")
    .trim()
    .slice(0, USERNAME_MAX_LENGTH);
}

function SelectedMember({ member, onChange }) {
  const named = Boolean(member?.display_name || member?.username);
  return (
    <div className="cz-create-member">
      <MemberAvatar member={member} size={48} />
      <span className="cz-create-member-copy">
        <strong className={named ? undefined : "cz-mono"}>{memberName(member)}</strong>
        {memberHandle(member) && <span>{memberHandle(member)}</span>}
        {named && member?.id && <span className="cz-mono">ID {member.id}</span>}
      </span>
      {onChange && (
        <button type="button" className="cz-button cz-button--compact" onClick={onChange}>
          Changer
        </button>
      )}
    </div>
  );
}

// Monté seulement quand la modale est ouverte (Dialog.Portal) : chaque ouverture repart d'un état vierge.
function CreateCasierContent({ initialMember, onCreated }) {
  const queryClient = useQueryClient();
  const baseId = useId();
  const ids = {
    search: `${baseId}-search`,
    searchHint: `${baseId}-search-hint`,
    listbox: `${baseId}-listbox`,
    discordId: `${baseId}-discord-id`,
    discordIdHint: `${baseId}-discord-id-hint`,
    username: `${baseId}-username`,
    usernameHint: `${baseId}-username-hint`,
  };
  const optionId = (index) => `${baseId}-option-${index}`;

  const searchRef = useRef(null);
  const discordIdRef = useRef(null);
  const usernameRef = useRef(null);
  const submitRef = useRef(null);
  const pendingFocusRef = useRef(null);

  const [chosenMode, setChosenMode] = useState(MODE_MEMBER);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState(EMPTY_SEARCH);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [listDismissed, setListDismissed] = useState(false);
  const [selected, setSelected] = useState(null);
  const [discordId, setDiscordId] = useState("");
  const [username, setUsername] = useState("");
  const [touched, setTouched] = useState({});
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const mode = initialMember ? "initial" : chosenMode;
  // Signalement sans auteur connu : seul l'ID est fourni, le pseudo se saisit à la main.
  const initialName = mode === "initial" ? memberUsername(initialMember) : "";
  const term = query.trim();
  const searchable = mode === MODE_MEMBER && !selected && term.length >= MEMBER_SEARCH_MIN_LENGTH;
  const settled = search.term === term;
  const searching = searchable && !settled;
  const results = searchable ? search.results : [];
  const listVisible = searchable && !listDismissed;
  const activeOption = activeIndex >= 0 && activeIndex < results.length ? activeIndex : -1;

  // Recherche Discord : 250 ms après la dernière frappe, la requête précédente est annulée.
  useEffect(() => {
    if (!searchable) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const found = await searchMembers(term, { signal: controller.signal });
        setSearch({ term, results: Array.isArray(found) ? found : [], error: null });
      } catch (error) {
        if (controller.signal.aborted) return;
        setSearch({ term, results: [], error: errorMessage(error) });
      }
      setActiveIndex(-1);
    }, MEMBER_SEARCH_DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [term, searchable]);

  // Focus déplacé après un changement de mode ou de membre (le champ visé vient d'être rendu).
  useEffect(() => {
    const target = pendingFocusRef.current;
    if (!target) return;
    pendingFocusRef.current = null;
    target.current?.focus();
  });

  const activeOptionId = listVisible && activeOption >= 0 ? optionId(activeOption) : undefined;

  useEffect(() => {
    if (!activeOptionId) return;
    document.getElementById(activeOptionId)?.scrollIntoView?.({ block: "nearest" });
  }, [activeOptionId]);

  const switchMode = (next) => {
    if (next === chosenMode || submitting) return;
    // Préremplit la prévention avec ce qui a déjà été saisi ou choisi.
    if (next === MODE_PREVENTION && selected) {
      if (!discordId) setDiscordId(String(selected.id));
      if (!username) setUsername(memberUsername(selected));
    } else if (next === MODE_PREVENTION && term) {
      if (DISCORD_ID_PATTERN.test(term)) {
        if (!discordId) setDiscordId(term);
      } else if (!username) {
        setUsername(term.slice(0, USERNAME_MAX_LENGTH));
      }
    }
    setChosenMode(next);
    setAttempted(false);
    setFormError(null);
    pendingFocusRef.current = next === MODE_PREVENTION ? discordIdRef : selected ? submitRef : searchRef;
  };

  const pickMember = (member) => {
    if (!member?.id) return;
    setSelected(member);
    setActiveIndex(-1);
    setFormError(null);
    pendingFocusRef.current = submitRef;
  };

  const changeMember = () => {
    setSelected(null);
    setListDismissed(false);
    setFormError(null);
    pendingFocusRef.current = searchRef;
  };

  const handleSearchKeyDown = (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!searchable || results.length === 0) return;
      event.preventDefault();
      setListDismissed(false);
      const count = results.length;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActiveIndex((current) => {
        const from = current >= 0 && current < count ? current : step > 0 ? -1 : count;
        return (from + step + count) % count;
      });
      return;
    }

    // Entrée choisit le membre actif (ou l'unique résultat) au lieu d'envoyer le formulaire.
    if (event.key === "Enter") {
      event.preventDefault();
      const member =
        listVisible && activeOption >= 0 ? results[activeOption] : listVisible && results.length === 1 ? results[0] : null;
      if (member) pickMember(member);
      else setAttempted(true);
    }
  };

  const discordIdValue = discordId.trim();
  const usernameValue = username.trim();
  const discordIdError = !discordIdValue
    ? "Indiquez l'ID Discord du membre."
    : DISCORD_ID_PATTERN.test(discordIdValue)
      ? null
      : "L'ID Discord compte 17 à 20 chiffres.";
  const usernameError = usernameValue ? null : "Indiquez un pseudo.";
  const showDiscordIdError = Boolean(discordIdError) && (attempted || touched.discordId);
  const showUsernameError = Boolean(usernameError) && (attempted || touched.username);
  const memberError = mode === MODE_MEMBER && attempted && !selected ? "Choisissez un membre dans la liste." : null;
  const initialError =
    mode === "initial" && !DISCORD_ID_PATTERN.test(String(initialMember?.id ?? ""))
      ? "Identifiant Discord invalide : impossible de créer ce casier."
      : null;

  // { payload } si le formulaire est valide, sinon { invalid } : le champ à corriger.
  const buildPayload = () => {
    if (mode === "initial") {
      if (initialError) return {};
      return {
        payload: {
          discord_id: String(initialMember.id),
          username: initialName || usernameValue.slice(0, USERNAME_MAX_LENGTH),
        },
      };
    }
    if (mode === MODE_MEMBER) {
      if (!selected?.id) return { invalid: searchRef };
      // Le pseudo ne sert que si le membre a quitté le serveur entre-temps (casier en prévention).
      return { payload: { discord_id: String(selected.id), username: memberUsername(selected) } };
    }
    if (discordIdError) return { invalid: discordIdRef };
    if (usernameError) return { invalid: usernameRef };
    return { payload: { discord_id: discordIdValue, username: usernameValue.slice(0, USERNAME_MAX_LENGTH) } };
  };

  const finish = (casierId, message) => {
    queryClient.invalidateQueries({ queryKey: casierKeys.lists() });
    toast.success(message);
    onCreated?.(casierId);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setAttempted(true);
    setFormError(null);
    const { payload, invalid } = buildPayload();
    if (!payload) {
      invalid?.current?.focus();
      return;
    }

    setSubmitting(true);
    try {
      const created = await createCasier(payload);
      const casierId = created?.id;
      let isPrevention = mode === MODE_PREVENTION;
      // Le détail dit si le serveur a choisi la prévention ; il sert aussi de cache pour l'ouverture du casier.
      if (casierId) {
        try {
          const detail = await getCasier(casierId);
          if (detail) {
            queryClient.setQueryData(casierKeys.detail(casierId), detail);
            isPrevention = Boolean(detail.is_prevention);
          }
        } catch {
          // Casier bien créé : le détail se chargera à l'ouverture.
        }
      }
      finish(casierId, isPrevention ? "Casier créé en prévention." : "Casier créé.");
    } catch (error) {
      if (isApiError(error, 409)) {
        try {
          const existing = await findCasierByDiscordId(payload.discord_id);
          if (existing?.id) {
            finish(existing.id, "Ce membre a déjà un casier : il est ouvert.");
            return;
          }
        } catch {
          // Message standard ci-dessous.
        }
      }
      setFormError(errorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  const blockWhileSubmitting = (event) => {
    if (submitting) event.preventDefault();
  };

  const handleEscape = (event) => {
    if (submitting) {
      event.preventDefault();
      return;
    }
    // Échap ferme d'abord la liste des membres, puis la modale.
    if (listVisible && document.activeElement === searchRef.current) {
      event.preventDefault();
      setListDismissed(true);
      setActiveIndex(-1);
    }
  };

  const handleOpenAutoFocus = (event) => {
    if (mode !== MODE_MEMBER) return;
    event.preventDefault();
    searchRef.current?.focus();
  };

  const resultsLabel = searching
    ? "Recherche en cours…"
    : search.error
      ? search.error
      : results.length > 0
        ? `${results.length} ${results.length > 1 ? "membres trouvés" : "membre trouvé"}`
        : "Aucun membre trouvé.";

  return (
    <Dialog.Content
      className="cz-dialog cz-create"
      onOpenAutoFocus={handleOpenAutoFocus}
      onEscapeKeyDown={handleEscape}
      onInteractOutside={blockWhileSubmitting}
    >
      <div className="cz-dialog-header">
        <div>
          <p className="cz-dialog-eyebrow">MODÉRATION</p>
          <Dialog.Title className="cz-dialog-title">Créer un casier</Dialog.Title>
        </div>
        <Dialog.Close asChild>
          <button type="button" className="cz-dialog-close" aria-label="Fermer" disabled={submitting}>
            <X size={18} aria-hidden="true" />
          </button>
        </Dialog.Close>
      </div>

      <form className="cz-create-form" onSubmit={handleSubmit} noValidate>
        <div className="cz-dialog-body">
          <Dialog.Description className="cz-dialog-description">
            Le casier regroupe les sanctions, les fiches S et les signalements IA d'un membre.
          </Dialog.Description>

          {mode === "initial" ? (
            <>
              <div className="cz-field">
                <span className="cz-label">Membre</span>
                <SelectedMember member={initialMember} />
              </div>
              {initialError ? (
                <p className="cz-callout cz-callout--red" role="alert">
                  <CircleAlert size={16} aria-hidden="true" />
                  <span>{initialError}</span>
                </p>
              ) : initialName ? (
                <p className="cz-callout">
                  <Info size={16} aria-hidden="true" />
                  <span>S'il a quitté le serveur, le casier est créé en prévention avec ce pseudo.</span>
                </p>
              ) : (
                <div className="cz-field">
                  <label className="cz-label" htmlFor={ids.username}>
                    Pseudo
                  </label>
                  <input
                    id={ids.username}
                    className="cz-input"
                    type="text"
                    autoComplete="off"
                    spellCheck={false}
                    maxLength={USERNAME_MAX_LENGTH}
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    aria-describedby={ids.usernameHint}
                    readOnly={submitting}
                  />
                  <p id={ids.usernameHint} className="cz-hint">
                    Nécessaire seulement si le membre a quitté le serveur : le casier est alors créé en prévention.
                  </p>
                </div>
              )}
            </>
          ) : (
            <>
              <div className="cz-create-modes" role="group" aria-label="Où se trouve le membre ?">
                <button
                  type="button"
                  className="cz-create-mode"
                  aria-pressed={mode === MODE_MEMBER}
                  onClick={() => switchMode(MODE_MEMBER)}
                  disabled={submitting}
                >
                  <UserRoundSearch size={18} aria-hidden="true" />
                  <span className="cz-create-mode-copy">
                    <strong>Sur le serveur</strong>
                    <small>Rechercher un membre</small>
                  </span>
                </button>
                <button
                  type="button"
                  className="cz-create-mode"
                  aria-pressed={mode === MODE_PREVENTION}
                  onClick={() => switchMode(MODE_PREVENTION)}
                  disabled={submitting}
                >
                  <UserX size={18} aria-hidden="true" />
                  <span className="cz-create-mode-copy">
                    <strong>Hors serveur</strong>
                    <small>Casier en prévention</small>
                  </span>
                </button>
              </div>

              {mode === MODE_MEMBER &&
                (selected ? (
                  <div className="cz-field">
                    <span className="cz-label">Membre sélectionné</span>
                    <SelectedMember member={selected} onChange={submitting ? null : changeMember} />
                  </div>
                ) : (
                  <div className="cz-field">
                    <label className="cz-label" htmlFor={ids.search}>
                      Membre Discord
                    </label>
                    <div className="cz-search cz-create-search">
                      <Search size={18} aria-hidden="true" />
                      <input
                        ref={searchRef}
                        id={ids.search}
                        type="search"
                        role="combobox"
                        value={query}
                        onChange={(event) => {
                          setQuery(event.target.value);
                          setListDismissed(false);
                        }}
                        onKeyDown={handleSearchKeyDown}
                        placeholder="Pseudo ou surnom sur le serveur"
                        autoComplete="off"
                        spellCheck={false}
                        enterKeyHint="search"
                        aria-autocomplete="list"
                        aria-expanded={listVisible}
                        aria-controls={ids.listbox}
                        aria-activedescendant={activeOptionId}
                        aria-describedby={ids.searchHint}
                        aria-invalid={memberError ? "true" : undefined}
                      />
                      {searching && <Loader2 size={16} className="cz-spin cz-create-spin" aria-hidden="true" />}
                    </div>
                    <p id={ids.searchHint} className={memberError ? "cz-field-error" : "cz-hint"}>
                      {memberError ||
                        `Tapez au moins ${MEMBER_SEARCH_MIN_LENGTH} caractères, puis choisissez un membre.`}
                    </p>

                    <span className="cz-sr-only" role="status">
                      {listVisible && (settled || results.length === 0) ? resultsLabel : ""}
                    </span>

                    <ul
                      id={ids.listbox}
                      className="cz-create-results"
                      role="listbox"
                      aria-label="Membres trouvés"
                      hidden={!listVisible || results.length === 0}
                    >
                      {results.map((member, index) => (
                        <li
                          key={member.id || index}
                          id={optionId(index)}
                          role="option"
                          aria-selected={index === activeOption}
                          className={`cz-create-option${index === activeOption ? " is-active" : ""}`}
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => pickMember(member)}
                        >
                          <MemberAvatar member={member} size={36} />
                          <span className="cz-create-option-copy">
                            <strong>{memberName(member)}</strong>
                            <span>
                              {[memberHandle(member), member.id ? `ID ${member.id}` : ""].filter(Boolean).join(" · ")}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ul>

                    {listVisible && results.length === 0 && (
                      <div className={`cz-create-results-state${search.error && settled ? " is-error" : ""}`}>
                        {searching ? (
                          <p>
                            <Loader2 size={16} className="cz-spin" aria-hidden="true" />
                            Recherche…
                          </p>
                        ) : search.error ? (
                          <p>
                            <CircleAlert size={16} aria-hidden="true" />
                            {search.error}
                          </p>
                        ) : (
                          <>
                            <p>Aucun membre trouvé.</p>
                            <p className="cz-meta">
                              Le membre n'est plus sur le serveur ?{" "}
                              <button type="button" className="cz-link" onClick={() => switchMode(MODE_PREVENTION)}>
                                Créer un casier en prévention
                              </button>
                            </p>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                ))}

              {mode === MODE_PREVENTION && (
                <>
                  <p className="cz-callout">
                    <Info size={16} aria-hidden="true" />
                    <span>
                      Pour un membre qui n'est pas (ou plus) sur le serveur : le casier est marqué « Prévention ». Si
                      Discord retrouve le membre, un casier normal est créé à la place.
                    </span>
                  </p>

                  <div className="cz-field">
                    <label className="cz-label" htmlFor={ids.discordId}>
                      ID Discord
                    </label>
                    <input
                      ref={discordIdRef}
                      id={ids.discordId}
                      className="cz-input cz-mono"
                      type="text"
                      inputMode="numeric"
                      autoComplete="off"
                      spellCheck={false}
                      value={discordId}
                      onChange={(event) =>
                        setDiscordId(event.target.value.replace(/\D/g, "").slice(0, DISCORD_ID_MAX_LENGTH))
                      }
                      onBlur={() => setTouched((current) => ({ ...current, discordId: true }))}
                      placeholder="1153638521786093580"
                      aria-invalid={showDiscordIdError ? "true" : undefined}
                      aria-describedby={ids.discordIdHint}
                      readOnly={submitting}
                    />
                    <p id={ids.discordIdHint} className={showDiscordIdError ? "cz-field-error" : "cz-hint"}>
                      {showDiscordIdError
                        ? discordIdError
                        : "17 à 20 chiffres : clic droit sur le membre dans Discord, puis « Copier l'identifiant »."}
                    </p>
                  </div>

                  <div className="cz-field">
                    <label className="cz-label" htmlFor={ids.username}>
                      Pseudo
                    </label>
                    <input
                      ref={usernameRef}
                      id={ids.username}
                      className="cz-input"
                      type="text"
                      autoComplete="off"
                      spellCheck={false}
                      maxLength={USERNAME_MAX_LENGTH}
                      value={username}
                      onChange={(event) => setUsername(event.target.value)}
                      onBlur={() => setTouched((current) => ({ ...current, username: true }))}
                      placeholder="nova.lune"
                      aria-invalid={showUsernameError ? "true" : undefined}
                      aria-describedby={ids.usernameHint}
                      readOnly={submitting}
                    />
                    <p id={ids.usernameHint} className={showUsernameError ? "cz-field-error" : "cz-hint"}>
                      {showUsernameError ? usernameError : "Nom affiché dans le casier tant que le membre est absent."}
                    </p>
                  </div>
                </>
              )}
            </>
          )}

          {formError && (
            <p className="cz-callout cz-callout--red" role="alert">
              <CircleAlert size={16} aria-hidden="true" />
              <span>{formError}</span>
            </p>
          )}
        </div>

        <div className="cz-dialog-footer">
          <Dialog.Close asChild>
            <button type="button" className="cz-button" disabled={submitting}>
              Annuler
            </button>
          </Dialog.Close>
          <button
            ref={submitRef}
            type="submit"
            className="cz-button cz-button--primary"
            disabled={submitting || Boolean(initialError)}
            aria-busy={submitting || undefined}
          >
            {submitting ? (
              <Loader2 size={16} className="cz-spin" aria-hidden="true" />
            ) : (
              <ShieldCheck size={16} aria-hidden="true" />
            )}
            {submitting ? "Création…" : "Créer le casier"}
          </button>
        </div>
      </form>
    </Dialog.Content>
  );
}

export default function CreateCasierModal({ open, onClose, onCreated, initialMember }) {
  return (
    <Dialog.Root
      open={Boolean(open)}
      onOpenChange={(next) => {
        if (!next) onClose?.();
      }}
    >
      <Dialog.Portal>
        <div className="cz-dialog-root">
          <Dialog.Overlay className="cz-dialog-overlay" />
          <CreateCasierContent initialMember={initialMember || null} onCreated={onCreated} />
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
