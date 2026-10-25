import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Eye, FileLock2, Lock, PenLine, ScrollText } from "lucide-react";

import "./casier-fiches-ia.css";
import ConfirmDialog from "./ConfirmDialog";
import FicheSContent from "./FicheSContent";
import FicheSEditorDialog, { restoreFocusLater } from "./FicheSEditorDialog";
import StatusPill from "./StatusPill";
import { casierKeys, closeFiche, errorMessage } from "./casierApi";
import { authorName, formatDate, plural } from "./formatters";

function timeOf(value) {
  const time = Date.parse(value || "");
  return Number.isFinite(time) ? time : 0;
}

// Actives d'abord, puis de la plus récente à la plus ancienne (même ordre que l'API).
function sortFiches(fiches) {
  return [...fiches].sort((a, b) => {
    if (Boolean(a?.active) !== Boolean(b?.active)) return a?.active ? -1 : 1;
    return timeOf(b?.created_at) - timeOf(a?.created_at);
  });
}

function findCard(root, ficheId) {
  if (!root || !ficheId) return null;
  return Array.from(root.querySelectorAll("[data-fiche-id]")).find(
    (node) => node.getAttribute("data-fiche-id") === ficheId
  );
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

function LockHint({ closed }) {
  const tipId = useId();
  const text = closed
    ? "Seul un Responsable peut modifier une fiche S clôturée."
    : "Seul l'auteur ou un Responsable peut modifier cette fiche.";
  return (
    <span className="cz-fiche-lock" tabIndex={0} aria-describedby={tipId}>
      <Lock size={15} aria-hidden="true" />
      <span className="cz-sr-only">Modification réservée</span>
      <span role="tooltip" id={tipId} className="cz-fiche-lock-tip">
        {text}
      </span>
    </span>
  );
}

function FicheCard({ fiche, highlighted, onEdit, onClose, closing }) {
  const active = Boolean(fiche.active);
  const revisions = Number(fiche.revisions_count) || 0;
  const updated = Boolean(fiche.updated_at);

  return (
    <article
      className={`cz-fiche-card${active ? "" : " cz-fiche-card--closed"}${highlighted ? " cz-target" : ""}`}
      data-fiche-id={fiche.id}
      aria-label={`Fiche S : ${fiche.title || "sans titre"}`}
    >
      <header className="cz-fiche-head">
        <div className="cz-fiche-heading">
          <h3 className="cz-fiche-title">{fiche.title || "Fiche sans titre"}</h3>
          {active ? (
            <StatusPill variant="fiche" size="sm" icon={Eye}>
              Active
            </StatusPill>
          ) : (
            <StatusPill variant="neutral" size="sm" icon={FileLock2}>
              Clôturée
            </StatusPill>
          )}
        </div>

        <div className="cz-fiche-actions">
          {fiche.can_edit ? (
            <button type="button" className="cz-button cz-button--compact" onClick={() => onEdit(fiche)}>
              <PenLine size={15} aria-hidden="true" />
              Modifier
            </button>
          ) : (
            <LockHint closed={!active} />
          )}
          {active && (
            <button
              type="button"
              className="cz-button cz-button--compact cz-button--fiche"
              onClick={() => onClose(fiche)}
              disabled={closing}
            >
              Clôturer
            </button>
          )}
        </div>
      </header>

      <div className="cz-fiche-body">
        <FicheSContent fiche={fiche} />
      </div>

      <footer className="cz-fiche-foot">
        <span>
          Rédigée par {authorName(fiche.created_by)} · {formatDate(fiche.created_at)}
        </span>
        {updated && (
          <span>
            Modifiée par {authorName(fiche.updated_by)} · {formatDate(fiche.updated_at)}
            {revisions > 0 &&
              ` · ${plural(revisions, "version précédente conservée", "versions précédentes conservées")}`}
          </span>
        )}
        {!active && (
          <span>
            Clôturée par {authorName(fiche.closed_by)}
            {fiche.closed_at ? ` · ${formatDate(fiche.closed_at)}` : ""}
          </span>
        )}
      </footer>
    </article>
  );
}

// Onglet « Fiches S » du détail. Gère la clôture et sa propre modale d'édition ;
// `onCreate` / `onEdit` permettent au parent d'utiliser une modale partagée à la place.
export default function FicheSList({ casier, highlightFicheId = null, onCreate, onEdit }) {
  const queryClient = useQueryClient();
  const casierId = casier?.id ?? null;
  const fiches = useMemo(
    () => sortFiches(Array.isArray(casier?.fiches_s) ? casier.fiches_s.filter(Boolean) : []),
    [casier?.fiches_s]
  );

  const [editor, setEditor] = useState({ open: false, fiche: null });
  const [toClose, setToClose] = useState(null);
  const listRef = useRef(null);
  const scrolledRef = useRef(null);
  const closeReturnRef = useRef(null);

  const askClose = (fiche) => {
    closeReturnRef.current = document.activeElement;
    setToClose(fiche);
  };

  const cancelClose = () => {
    setToClose(null);
    restoreFocusLater(closeReturnRef.current);
  };

  const openCreate = () => {
    if (onCreate) onCreate();
    else setEditor({ open: true, fiche: null });
  };

  const openEdit = (fiche) => {
    if (onEdit) onEdit(fiche);
    else setEditor({ open: true, fiche });
  };

  const closeEditor = () => setEditor((current) => ({ ...current, open: false }));

  const closeMutation = useMutation({
    mutationFn: (fiche) => closeFiche(casierId, fiche.id),
    onSuccess: (detail, fiche) => {
      if (detail) queryClient.setQueryData(casierKeys.detail(casierId), detail);
      queryClient.invalidateQueries({ queryKey: casierKeys.lists() });
      toast.success("Fiche S clôturée.");
      setToClose(null);
      // Le bouton « Clôturer » a disparu : le focus revient sur la carte de la fiche.
      window.setTimeout(() => {
        const card = findCard(listRef.current, fiche?.id);
        const target = card?.querySelector("button, [tabindex='0']");
        if (target) target.focus();
      }, 0);
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });

  // Fiche ciblée : défilement une seule fois quand elle est rendue (et visible).
  useEffect(() => {
    if (!highlightFicheId) {
      scrolledRef.current = null;
      return;
    }
    if (scrolledRef.current === highlightFicheId) return;
    const card = findCard(listRef.current, highlightFicheId);
    if (!card || card.offsetParent === null) return;
    scrolledRef.current = highlightFicheId;
    card.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [highlightFicheId, fiches]);

  const activeCount = fiches.filter((fiche) => fiche.active).length;

  return (
    <div className="cz-fiche-list" ref={listRef}>
      <div className="cz-callout cz-callout--violet cz-fiche-intro">
        <ScrollText size={18} aria-hidden="true" />
        <p>
          Une fiche S documente un comportement à suivre. Elle ne change pas le statut du membre.
          {fiches.length > 0 && (
            <span className="cz-fiche-intro-count">
              {" "}
              {plural(activeCount, "fiche active", "fiches actives")} sur {fiches.length}.
            </span>
          )}
        </p>
        {casierId && (
          <button type="button" className="cz-button cz-button--compact cz-button--fiche" onClick={openCreate}>
            <PenLine size={15} aria-hidden="true" />
            Rédiger une fiche S
          </button>
        )}
      </div>

      {fiches.length === 0 ? (
        <div className="cz-empty cz-empty--compact">
          <ScrollText size={26} aria-hidden="true" />
          <h3>Aucune fiche S pour ce membre.</h3>
        </div>
      ) : (
        fiches.map((fiche) => (
          <FicheCard
            key={fiche.id}
            fiche={fiche}
            highlighted={Boolean(highlightFicheId) && fiche.id === highlightFicheId}
            onEdit={openEdit}
            onClose={askClose}
            closing={closeMutation.isPending && closeMutation.variables?.id === fiche.id}
          />
        ))
      )}

      <ConfirmDialog
        open={Boolean(toClose)}
        eyebrow="Fiche S"
        title="Clôturer cette fiche S ?"
        description={`« ${toClose?.title || "Fiche sans titre"} » restera visible dans le casier, marquée « Clôturée ». Seul un Responsable pourra encore la modifier.`}
        confirmLabel="Clôturer"
        tone="fiche"
        pending={closeMutation.isPending}
        onConfirm={() => toClose && closeMutation.mutate(toClose)}
        onCancel={cancelClose}
      />

      {!onCreate || !onEdit ? (
        <FicheSEditorDialog
          open={editor.open}
          casierId={casierId}
          casier={casier}
          fiche={editor.fiche}
          onClose={closeEditor}
        />
      ) : null}
    </div>
  );
}
