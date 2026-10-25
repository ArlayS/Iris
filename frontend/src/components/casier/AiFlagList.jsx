import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Bot, Loader2, Pin } from "lucide-react";

import CreateCasierModal from "../CreateCasierModal";

import "./casier-fiches-ia.css";
import AddSanctionDialog from "./AddSanctionDialog";
import AiFlagCard from "./AiFlagCard";
import { casierKeys, errorMessage, getAiFlag, getCasier, isApiError, listAiFlags } from "./casierApi";
import { AI_FLAGS_PAGE_SIZE } from "./casierConstants";

const ID_PATTERN = /^[0-9a-f]{24}$/;
const MAX_SKIP = 10000;
const EXPIRED_MESSAGE = "Ce signalement n'existe plus (expiré ou supprimé).";

// Pas de nouvel essai sur une erreur 4xx (422 d'un filtre, 404…).
function retryServerErrors(failureCount, error) {
  const status = error?.response?.status;
  if (status && status < 500) return false;
  return failureCount < 2;
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

// `discord_id` présent mais vide (membre inconnu) : aucune requête, sinon on listerait tous les signalements.
function isBlocked(params) {
  return Boolean(params) && Object.prototype.hasOwnProperty.call(params, "discord_id") && !params.discord_id;
}

// Pages de signalements (+30 par « Charger plus »). Partagé par la liste et la vue globale (compteurs) :
// même clé, donc une seule requête.
export function useAiFlagPages(params) {
  const safeParams = params || {};
  return useInfiniteQuery({
    queryKey: [...casierKeys.aiFlagList(safeParams), "pages"],
    queryFn: ({ pageParam, signal }) =>
      listAiFlags({ ...safeParams, skip: pageParam, limit: AI_FLAGS_PAGE_SIZE }, { signal }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) => {
      const loaded = pages.reduce((count, page) => count + (page?.items?.length || 0), 0);
      if (!lastPage?.items?.length || loaded >= (lastPage.total || 0) || loaded > MAX_SKIP) return undefined;
      return loaded;
    },
    placeholderData: keepPreviousData,
    enabled: !isBlocked(safeParams),
    retry: retryServerErrors,
  });
}

function findItem(root, flagId) {
  if (!root || !flagId) return null;
  return Array.from(root.querySelectorAll("[data-flag-id]")).find(
    (node) => node.getAttribute("data-flag-id") === flagId
  );
}

function focusFirstAction(item) {
  const target = item?.querySelector("button:not([disabled]), a[href]");
  if (target) target.focus();
  return Boolean(target);
}

function flattenItems(pages) {
  const seen = new Set();
  const items = [];
  (pages || []).forEach((page) => {
    (page?.items || []).forEach((item) => {
      if (!item?.id || seen.has(item.id)) return;
      seen.add(item.id);
      items.push(item);
    });
  });
  return items;
}

function ListSkeleton() {
  return (
    <div className="cz-flag-list" aria-hidden="true">
      {[0, 1, 2].map((index) => (
        <div key={index} className="cz-flag-card cz-flag-card--ia-0 cz-flag-skeleton">
          <div className="cz-skeleton-row cz-skeleton-row--flush">
            <span className="cz-skeleton cz-skeleton--circle" />
            <div className="cz-skeleton-stack">
              <span className="cz-skeleton cz-skeleton--title" />
              <span className="cz-skeleton cz-skeleton--short" />
            </div>
          </div>
          <span className="cz-skeleton cz-skeleton--block" />
        </div>
      ))}
    </div>
  );
}

// Liste de signalements IA avec « Charger plus », ciblage d'un signalement et parcours « Sanctionner ».
export default function AiFlagList({
  params,
  compact = false,
  highlightFlagId = null,
  onNavigate,
  emptyMessage = "Aucun signalement pour ces filtres.",
}) {
  const queryClient = useQueryClient();
  const query = useAiFlagPages(params);
  const blocked = isBlocked(params);
  const items = useMemo(() => flattenItems(query.data?.pages), [query.data]);
  const total = query.data?.pages?.[0]?.total ?? items.length;

  const targetId = highlightFlagId && ID_PATTERN.test(highlightFlagId) ? highlightFlagId : null;
  const targetInList = Boolean(targetId) && items.some((item) => item.id === targetId);

  // Signalement ciblé absent de la page chargée : affiché en tête.
  const pinnedQuery = useQuery({
    queryKey: casierKeys.aiFlag(targetId),
    queryFn: ({ signal }) => getAiFlag(targetId, { signal }),
    enabled: Boolean(targetId) && query.isSuccess && !query.isPlaceholderData && !targetInList,
    retry: retryServerErrors,
  });
  const pinned = targetId && !targetInList && pinnedQuery.data?.id === targetId ? pinnedQuery.data : null;

  const expiredToastRef = useRef(new Set());
  useEffect(() => {
    if (!targetId || !pinnedQuery.isError || expiredToastRef.current.has(targetId)) return;
    expiredToastRef.current.add(targetId);
    toast.error(isApiError(pinnedQuery.error, 404) ? EXPIRED_MESSAGE : errorMessage(pinnedQuery.error));
  }, [targetId, pinnedQuery.isError, pinnedQuery.error]);

  // Défilement une seule fois vers la carte ciblée, quand elle est rendue et visible.
  const listRef = useRef(null);
  const scrolledRef = useRef(null);
  useEffect(() => {
    if (!targetId) {
      scrolledRef.current = null;
      return;
    }
    if (scrolledRef.current === targetId) return;
    const node = findItem(listRef.current, targetId);
    if (!node || node.offsetParent === null) return;
    scrolledRef.current = targetId;
    node.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [targetId, items, pinned]);

  // Carte qui contenait le focus : si elle quitte la liste filtrée (revue changée), le focus passe à la suivante.
  const focusedRef = useRef(null);
  const rememberFocus = (event) => {
    const item = event.target?.closest?.("[data-flag-id]");
    if (!item || item.parentElement !== listRef.current) return;
    focusedRef.current = {
      id: item.getAttribute("data-flag-id"),
      index: Array.prototype.indexOf.call(listRef.current.children, item),
    };
  };

  useEffect(() => {
    const last = focusedRef.current;
    if (!last || items.some((item) => item.id === last.id)) return;
    focusedRef.current = null;
    const active = document.activeElement;
    if (active && active !== document.body && active.isConnected) return;
    const nodes = listRef.current ? Array.from(listRef.current.children) : [];
    focusFirstAction(nodes[Math.min(last.index, nodes.length - 1)]);
  }, [items]);

  /* Parcours « Sanctionner » et « Créer le casier » */

  const [sanction, setSanction] = useState(null);
  const [creation, setCreation] = useState(null);
  const [preparing, setPreparing] = useState(false);
  const dialogReturnRef = useRef(null);

  // Radix ne rend le focus qu'à un Dialog.Trigger : retour au bouton d'origine, sinon à la carte.
  const returnFocus = (flagId) => {
    const origin = dialogReturnRef.current;
    dialogReturnRef.current = null;
    window.setTimeout(() => {
      if (origin && origin !== document.body && origin.isConnected) {
        origin.focus();
        return;
      }
      focusFirstAction(findItem(listRef.current, flagId));
    }, 0);
  };

  const closeSanction = () => {
    if (!sanction) return;
    const flagId = sanction.flag?.id;
    setSanction(null);
    returnFocus(flagId);
  };

  const cancelCreation = () => {
    if (!creation) return;
    const flagId = creation.flag?.id;
    setCreation(null);
    returnFocus(flagId);
  };

  const casierFor = (flag) =>
    queryClient.getQueryData(casierKeys.detail(flag.casier_id)) || {
      id: flag.casier_id,
      member: flag.author || { id: flag.discord_id },
      status: flag.casier_status || "vierge",
    };

  const startSanction = (flag) => {
    dialogReturnRef.current = document.activeElement;
    if (flag.casier_id) setSanction({ flag, casier: casierFor(flag) });
    else setCreation({ flag, next: "sanction" });
  };

  const startCreate = (flag) => {
    dialogReturnRef.current = document.activeElement;
    setCreation({ flag, next: "open" });
  };

  const handleCreated = async (created) => {
    const current = creation;
    const casierId = typeof created === "string" ? created : created?.id;
    setCreation(null);
    queryClient.invalidateQueries({ queryKey: casierKeys.aiFlags() });
    queryClient.invalidateQueries({ queryKey: casierKeys.lists() });
    if (!current || !casierId || !ID_PATTERN.test(casierId)) return;

    if (current.next === "open") {
      dialogReturnRef.current = null;
      onNavigate?.({ casier: casierId });
      return;
    }

    // Statut réel du casier (un casier existant a pu être retrouvé après un 409) pour l'aperçu de la modale.
    let casier = { id: casierId, member: current.flag.author || { id: current.flag.discord_id }, status: "vierge" };
    setPreparing(true);
    try {
      const detail = await queryClient.fetchQuery({
        queryKey: casierKeys.detail(casierId),
        queryFn: ({ signal }) => getCasier(casierId, { signal }),
      });
      if (detail?.id) casier = detail;
    } catch {
      // Repli : aperçu calculé depuis un casier vierge.
    } finally {
      setPreparing(false);
    }
    setSanction({ flag: { ...current.flag, casier_id: casierId }, casier });
  };

  const renderCard = (flag, isPinned = false) => (
    <li key={flag.id} className="cz-flag-item" data-flag-id={flag.id}>
      {isPinned && (
        <p className="cz-flag-pinned">
          <Pin size={13} aria-hidden="true" />
          Signalement ciblé par le lien
        </p>
      )}
      <AiFlagCard
        flag={flag}
        compact={compact}
        highlighted={flag.id === targetId}
        onNavigate={onNavigate}
        onSanction={startSanction}
        onCreateCasier={startCreate}
      />
    </li>
  );

  let body;
  if (blocked) {
    body = (
      <div className="cz-empty cz-empty--compact">
        <Bot size={26} aria-hidden="true" />
        <h3>{emptyMessage}</h3>
      </div>
    );
  } else if (query.isPending) {
    body = <ListSkeleton />;
  } else if (query.isError && !query.data) {
    body = (
      <div className="cz-empty cz-empty--error" role="alert">
        <Bot size={26} aria-hidden="true" />
        <h3>Impossible de charger les signalements.</h3>
        <p>{errorMessage(query.error)}</p>
        <div className="cz-empty-actions">
          <button type="button" className="cz-button" onClick={() => query.refetch()}>
            Réessayer
          </button>
        </div>
      </div>
    );
  } else if (!items.length && !pinned) {
    body = (
      <div className="cz-empty cz-empty--compact">
        <Bot size={26} aria-hidden="true" />
        <h3>{emptyMessage}</h3>
      </div>
    );
  } else {
    body = (
      <>
        <ul
          ref={listRef}
          className={`cz-flag-list${compact ? " cz-flag-list--compact" : ""}`}
          aria-busy={query.isPlaceholderData || undefined}
          onFocusCapture={rememberFocus}
        >
          {pinned && renderCard(pinned, true)}
          {items.map((flag) => renderCard(flag))}
        </ul>

        <div className="cz-flag-more-bar">
          <p className="cz-meta" role="status" aria-live="polite">
            {items.length} sur {total}
          </p>
          {query.hasNextPage && (
            <button
              type="button"
              className="cz-button cz-button--compact"
              onClick={() => query.fetchNextPage()}
              disabled={query.isFetchingNextPage}
              aria-busy={query.isFetchingNextPage || undefined}
            >
              {query.isFetchingNextPage && <Loader2 size={15} className="cz-spin" aria-hidden="true" />}
              Charger plus
            </button>
          )}
        </div>
      </>
    );
  }

  return (
    <div className={`cz-flags${compact ? " cz-flags--compact" : ""}${query.isPlaceholderData ? " is-updating" : ""}`}>
      {body}

      {preparing && (
        <p className="cz-meta cz-flag-preparing" role="status">
          <Loader2 size={14} className="cz-spin" aria-hidden="true" />
          Ouverture du casier…
        </p>
      )}

      <AddSanctionDialog
        open={Boolean(sanction)}
        casier={sanction?.casier || null}
        aiFlag={sanction?.flag || null}
        onClose={closeSanction}
        onSaved={closeSanction}
      />

      <CreateCasierModal
        open={Boolean(creation)}
        initialMember={creation?.flag?.author || (creation ? { id: creation.flag.discord_id } : undefined)}
        onClose={cancelCreation}
        onCreated={handleCreated}
      />
    </div>
  );
}
