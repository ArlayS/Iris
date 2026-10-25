import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { History, Loader2, Lock, X } from "lucide-react";

import TiptapSummaryEditor from "../TiptapSummaryEditor";

import "./casier-fiches-ia.css";
import ConfirmDialog from "./ConfirmDialog";
import { casierKeys, createFiche, errorMessage, isApiError, updateFiche } from "./casierApi";
import {
  FICHE_CONTENT_MAX_LENGTH,
  FICHE_DRAFT_SAVE_INTERVAL_MS,
  FICHE_EDITOR_PLACEHOLDER,
  FICHE_TITLE_MAX_LENGTH,
} from "./casierConstants";
import {
  clearFicheDraft,
  editorValueFor,
  isDraftNewer,
  isEditorEmpty,
  readFicheDraft,
  writeFicheDraft,
} from "./ficheContent";
import { formatDate, formatTime, memberName } from "./formatters";

// Menus flottants de BlockNote : Échap les ferme, il ne doit pas fermer la modale.
const EDITOR_MENU_SELECTOR = [
  ".bn-suggestion-menu",
  ".bn-grid-suggestion-menu",
  ".bn-toolbar",
  ".bn-formatting-toolbar",
  ".bn-link-toolbar",
  ".bn-panel",
  ".bn-table-handle-menu",
  "[role='menu']",
].join(", ");

// Radix ne rend le focus qu'à un Dialog.Trigger : on le rend nous-mêmes, après la fermeture.
export function restoreFocusLater(element) {
  if (!element || element === document.body || typeof element.focus !== "function") return;
  window.setTimeout(() => {
    if (element.isConnected) element.focus();
  }, 0);
}

function initialState(casierId, fiche) {
  const draft = readFicheDraft(casierId, fiche?.id);
  const restored = isDraftNewer(draft, fiche) ? draft : null;
  return {
    draft: restored,
    value: restored ? restored.content : editorValueFor(fiche),
    title: restored ? restored.title : fiche?.title ?? "",
  };
}

function FicheSEditorForm({ casierId, casier, fiche, closeRef, onClose, onSaved, onCloseAutoFocus }) {
  const queryClient = useQueryClient();
  const ficheId = fiche?.id ?? null;
  const isEdit = Boolean(ficheId);
  const baseId = useId();
  const titleInputId = `${baseId}-champ-titre`;
  const contentLabelId = `${baseId}-contenu`;
  const errorId = `${baseId}-erreur`;

  // Valeur initiale calculée une seule fois à l'ouverture (brouillon local s'il est plus récent).
  const [initial] = useState(() => initialState(casierId, fiche));
  const [initialValue, setInitialValue] = useState(initial.value);
  const [title, setTitle] = useState(initial.title);
  const [restoredDraft, setRestoredDraft] = useState(initial.draft);
  const [resetCount, setResetCount] = useState(0);
  const [contentDirty, setContentDirty] = useState(false);
  const [error, setError] = useState(null);
  const [readOnly, setReadOnly] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [draftSavedAt, setDraftSavedAt] = useState(null);

  const titleRef = useRef(null);
  const editorWrapRef = useRef(null);
  const contentRef = useRef(null);
  const interactedRef = useRef(false);
  const baselineRef = useRef(null);
  const draftTimerRef = useRef(null);
  const draftWrittenRef = useRef(false);
  const savedRef = useRef(false);
  const confirmReturnRef = useRef(null);
  const latest = useRef({});

  const originalTitle = fiche?.title ?? "";
  const titleChanged = title !== originalTitle;
  const dirty = titleChanged || contentDirty || Boolean(restoredDraft);

  const currentContent = useCallback(
    () => (contentRef.current !== null ? contentRef.current : initialValue),
    [initialValue]
  );

  useLayoutEffect(() => {
    latest.current = {
      title,
      currentContent,
      restored: Boolean(restoredDraft),
      userEdited: titleChanged || contentDirty,
    };
  });

  const writeDraftNow = useCallback(() => {
    if (draftTimerRef.current) {
      window.clearTimeout(draftTimerRef.current);
      draftTimerRef.current = null;
    }
    const state = latest.current;
    if (savedRef.current) return;
    if (!state.userEdited) {
      // Retour à la version d'origine : le brouillon écrit pendant cette ouverture n'a plus lieu d'être.
      if (draftWrittenRef.current && !state.restored) {
        clearFicheDraft(casierId, ficheId);
        draftWrittenRef.current = false;
        setDraftSavedAt(null);
      }
      return;
    }
    if (writeFicheDraft(casierId, ficheId, { title: state.title, content: state.currentContent() })) {
      draftWrittenRef.current = true;
      setDraftSavedAt(Date.now());
    }
  }, [casierId, ficheId]);

  // Au plus une écriture toutes les 2 s, seulement après une modification par l'utilisateur.
  const scheduleDraft = useCallback(() => {
    if (draftTimerRef.current || savedRef.current) return;
    draftTimerRef.current = window.setTimeout(writeDraftNow, FICHE_DRAFT_SAVE_INTERVAL_MS);
  }, [writeDraftNow]);

  const cancelDraftTimer = useCallback(() => {
    if (draftTimerRef.current) {
      window.clearTimeout(draftTimerRef.current);
      draftTimerRef.current = null;
    }
  }, []);

  // Fermeture de l'onglet ou démontage : le dernier état n'est pas perdu.
  useEffect(() => {
    const flush = () => {
      if (draftTimerRef.current) writeDraftNow();
    };
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, [writeDraftNow]);

  const markInteracted = useCallback(() => {
    interactedRef.current = true;
  }, []);

  // Le JSON est normalisé par l'éditeur : on ne compare jamais au contenu stocké, seulement à la référence
  // reçue avant la première interaction (si l'éditeur en envoie une au chargement).
  const handleEditorChange = useCallback(
    (json) => {
      contentRef.current = typeof json === "string" ? json : "";
      if (!interactedRef.current) {
        baselineRef.current = contentRef.current;
        return;
      }
      const changed = baselineRef.current === null ? true : contentRef.current !== baselineRef.current;
      setContentDirty(changed);
      if (changed) scheduleDraft();
    },
    [scheduleDraft]
  );

  const handleTitleChange = (event) => {
    setTitle(event.target.value);
    if (error?.field === "title") setError(null);
    scheduleDraft();
  };

  const focusEditor = () => {
    const editable = editorWrapRef.current?.querySelector('[contenteditable="true"]');
    if (editable) editable.focus();
  };

  const ignoreDraft = () => {
    cancelDraftTimer();
    clearFicheDraft(casierId, ficheId);
    draftWrittenRef.current = false;
    setRestoredDraft(null);
    setInitialValue(editorValueFor(fiche));
    setTitle(originalTitle);
    interactedRef.current = false;
    baselineRef.current = null;
    contentRef.current = null;
    setContentDirty(false);
    setDraftSavedAt(null);
    setError(null);
    setResetCount((count) => count + 1);
  };

  const mutation = useMutation({
    mutationFn: (body) => (isEdit ? updateFiche(casierId, ficheId, body) : createFiche(casierId, body)),
    onSuccess: (detail) => {
      savedRef.current = true;
      cancelDraftTimer();
      clearFicheDraft(casierId, ficheId);
      if (detail) queryClient.setQueryData(casierKeys.detail(casierId), detail);
      queryClient.invalidateQueries({ queryKey: casierKeys.lists() });
      toast.success(isEdit ? "Fiche S modifiée." : "Fiche S enregistrée.");
      onSaved?.(detail);
      onClose?.();
    },
    onError: (err) => {
      const message = errorMessage(err);
      setError({ field: null, message });
      toast.error(message);
      if (isApiError(err, 403)) {
        // Droits retirés entre-temps : la modale passe en lecture seule, le brouillon reste sur l'appareil.
        setReadOnly(true);
        queryClient.invalidateQueries({ queryKey: casierKeys.detail(casierId) });
      }
    },
  });
  const pending = mutation.isPending;

  const submit = (event) => {
    event?.preventDefault();
    if (pending || readOnly) return;

    const cleanTitle = title.trim();
    if (!cleanTitle) {
      setError({ field: "title", message: "Le titre est requis." });
      titleRef.current?.focus();
      return;
    }
    const content = currentContent();
    if (isEditorEmpty(content)) {
      setError({ field: "content", message: "Écris au moins une observation." });
      focusEditor();
      return;
    }
    if (content.length > FICHE_CONTENT_MAX_LENGTH) {
      setError({ field: "content", message: "La fiche S est trop longue (200 000 caractères maximum)." });
      return;
    }
    setError(null);

    if (!isEdit) {
      mutation.mutate({ title: cleanTitle, content });
      return;
    }
    const body = {};
    if (cleanTitle !== originalTitle) body.title = cleanTitle;
    if (contentDirty || restoredDraft) body.content = content;
    if (!Object.keys(body).length) {
      cancelDraftTimer();
      clearFicheDraft(casierId, ficheId);
      savedRef.current = true;
      toast("Aucune modification à enregistrer.");
      onClose?.();
      return;
    }
    mutation.mutate(body);
  };

  const requestClose = useCallback(() => {
    if (pending) return;
    if (dirty && !readOnly) {
      confirmReturnRef.current = document.activeElement;
      setConfirmClose(true);
      return;
    }
    onClose?.();
  }, [dirty, onClose, pending, readOnly]);

  useLayoutEffect(() => {
    closeRef.current = requestClose;
  });

  useLayoutEffect(
    () => () => {
      closeRef.current = null;
    },
    [closeRef]
  );

  // Fermeture confirmée : le brouillon reste sur cet appareil et sera proposé à la prochaine ouverture.
  const confirmDiscard = () => {
    if (draftTimerRef.current) writeDraftNow();
    setConfirmClose(false);
    onClose?.();
  };

  const handleEscape = (event) => {
    event.preventDefault();
    if (confirmClose) return;
    if (editorWrapRef.current?.querySelector(EDITOR_MENU_SELECTOR)) return;
    requestClose();
  };

  const member = casier?.member || queryClient.getQueryData(casierKeys.detail(casierId))?.member;
  const eyebrow = member ? `Fiche S · ${memberName(member)}` : "Fiche S";
  const titleCount = title.length;
  const revisions = Number(fiche?.revisions_count) || 0;

  let footerNote = null;
  if (readOnly) footerNote = "Lecture seule : rien ne sera enregistré.";
  else if (draftSavedAt) footerNote = `Brouillon enregistré sur cet appareil à ${formatTime(draftSavedAt)}.`;
  else if (isEdit) {
    footerNote =
      revisions > 0
        ? `La version actuelle sera conservée (${revisions} déjà).`
        : "La version actuelle sera conservée dans l'historique.";
  }

  return (
    <>
      <Dialog.Content
        className="cz-dialog cz-dialog--wide cz-fiche-dialog"
        aria-describedby={undefined}
        onEscapeKeyDown={handleEscape}
        onInteractOutside={(event) => event.preventDefault()}
        onCloseAutoFocus={onCloseAutoFocus}
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          titleRef.current?.focus();
        }}
      >
        <form className="cz-fiche-form" onSubmit={submit} noValidate>
          <div className="cz-dialog-header">
            <div>
              <p className="cz-dialog-eyebrow">{eyebrow}</p>
              <Dialog.Title className="cz-dialog-title">
                {isEdit ? "Modifier la fiche S" : "Rédiger une fiche S"}
              </Dialog.Title>
            </div>
            <button
              type="button"
              className="cz-dialog-close"
              onClick={requestClose}
              disabled={pending}
              aria-label="Fermer"
            >
              <X size={18} aria-hidden="true" />
            </button>
          </div>

          <div className="cz-dialog-body">
            {restoredDraft && !readOnly && (
              <div className="cz-callout cz-callout--violet cz-fiche-draft" role="status">
                <History size={18} aria-hidden="true" />
                <div className="cz-fiche-draft-copy">
                  <strong>Brouillon restauré</strong>
                  <span>
                    {restoredDraft.savedAt
                      ? `Version non enregistrée du ${formatDate(restoredDraft.savedAt)}.`
                      : "Version non enregistrée retrouvée sur cet appareil."}
                  </span>
                </div>
                <button type="button" className="cz-button cz-button--compact" onClick={ignoreDraft}>
                  Ignorer
                </button>
              </div>
            )}

            {readOnly && (
              <div className="cz-callout cz-callout--red" role="alert">
                <Lock size={18} aria-hidden="true" />
                <span>
                  {error?.message || "Vous ne pouvez plus modifier cette fiche S."} Votre texte reste affiché pour
                  que vous puissiez le copier ; le brouillon est gardé sur cet appareil.
                </span>
              </div>
            )}

            {error && !readOnly && !error.field && (
              <div className="cz-callout cz-callout--red" role="alert" id={errorId}>
                <span>{error.message}</span>
              </div>
            )}

            <div className="cz-field">
              <div className="cz-field-row">
                <label className="cz-label" htmlFor={titleInputId}>
                  Titre
                </label>
                <span className="cz-counter" aria-hidden="true">
                  {titleCount}/{FICHE_TITLE_MAX_LENGTH}
                </span>
              </div>
              <input
                ref={titleRef}
                id={titleInputId}
                className="cz-input cz-fiche-title-input"
                value={title}
                onChange={handleTitleChange}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    focusEditor();
                  }
                }}
                maxLength={FICHE_TITLE_MAX_LENGTH}
                placeholder="Ex. : Messages privés insistants envers les nouveaux"
                autoComplete="off"
                readOnly={readOnly}
                aria-invalid={error?.field === "title" || undefined}
                aria-describedby={error?.field === "title" ? errorId : undefined}
              />
              {error?.field === "title" && (
                <p className="cz-field-error" id={errorId}>
                  {error.message}
                </p>
              )}
            </div>

            <div className="cz-field cz-fiche-editor-field" role="group" aria-labelledby={contentLabelId}>
              <span className="cz-label" id={contentLabelId}>
                Observations
              </span>
              <div
                ref={editorWrapRef}
                className="cz-fiche-editor"
                onKeyDownCapture={markInteracted}
                onPointerDownCapture={markInteracted}
                onPasteCapture={markInteracted}
                onDropCapture={markInteracted}
              >
                <TiptapSummaryEditor
                  key={`${ficheId ?? "new"}:${resetCount}`}
                  value={initialValue}
                  onChange={handleEditorChange}
                  placeholder={FICHE_EDITOR_PLACEHOLDER}
                />
              </div>
              {error?.field === "content" ? (
                <p className="cz-field-error" id={errorId} role="alert">
                  {error.message}
                </p>
              ) : (
                <p className="cz-hint">
                  Une fiche S documente un comportement à suivre. Elle ne change pas le statut du membre.
                </p>
              )}
            </div>
          </div>

          <div className="cz-dialog-footer">
            {footerNote && <p className="cz-dialog-footer-note">{footerNote}</p>}
            <button type="button" className="cz-button" onClick={requestClose} disabled={pending}>
              {readOnly ? "Fermer" : "Annuler"}
            </button>
            {!readOnly && (
              <button
                type="submit"
                className="cz-button cz-button--primary"
                disabled={pending || (isEdit && !dirty)}
                aria-busy={pending || undefined}
              >
                {pending && <Loader2 size={16} className="cz-spin" aria-hidden="true" />}
                {isEdit ? "Enregistrer les modifications" : "Enregistrer la fiche S"}
              </button>
            )}
          </div>
        </form>
      </Dialog.Content>

      <ConfirmDialog
        open={confirmClose}
        title="Fermer sans enregistrer ?"
        description="Vos modifications ne sont pas enregistrées dans le casier. Le brouillon reste sur cet appareil et vous sera proposé à la prochaine ouverture."
        confirmLabel="Fermer"
        cancelLabel="Continuer la rédaction"
        tone="fiche"
        onConfirm={confirmDiscard}
        onCancel={() => {
          setConfirmClose(false);
          restoreFocusLater(confirmReturnRef.current);
        }}
      />
    </>
  );
}

// Création (fiche absente) et modification d'une fiche S. Le parent ferme la modale via `open`.
export default function FicheSEditorDialog({ open, casierId, casier = null, fiche = null, onClose, onSaved }) {
  const closeRef = useRef(null);
  const returnFocusRef = useRef(null);
  const resolvedCasierId = casierId ?? casier?.id ?? null;
  const isOpen = Boolean(open && resolvedCasierId);

  // Élément d'origine mémorisé avant que Radix ne place le focus dans la modale.
  useLayoutEffect(() => {
    if (isOpen) returnFocusRef.current = document.activeElement;
  }, [isOpen]);

  const restoreFocus = useCallback((event) => {
    event.preventDefault();
    const target = returnFocusRef.current;
    returnFocusRef.current = null;
    if (target && target !== document.body && target.isConnected) target.focus();
  }, []);

  return (
    <Dialog.Root
      open={isOpen}
      onOpenChange={(next) => {
        if (next) return;
        if (closeRef.current) closeRef.current();
        else onClose?.();
      }}
    >
      <Dialog.Portal>
        <div className="cz-dialog-root">
          <Dialog.Overlay className="cz-dialog-overlay" />
          <FicheSEditorForm
            casierId={resolvedCasierId}
            casier={casier}
            fiche={fiche}
            closeRef={closeRef}
            onClose={onClose}
            onSaved={onSaved}
            onCloseAutoFocus={restoreFocus}
          />
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
