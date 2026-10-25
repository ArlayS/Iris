import "./casier-detail.css";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, MessageSquarePlus, MessageSquareText } from "lucide-react";
import { toast } from "sonner";

import ConfirmDialog from "./ConfirmDialog";
import { addNote, casierKeys, deleteNote, errorMessage, updateNote } from "./casierApi";
import { NOTE_MAX_LENGTH } from "./casierConstants";
import { authorName, formatDate, plural } from "./formatters";

function isSubmitShortcut(event) {
  return event.key === "Enter" && (event.ctrlKey || event.metaKey);
}

// Champ de saisie partagé par l'ajout et la modification (Ctrl/Cmd + Entrée enregistre).
function NoteForm({ id, label, initialValue = "", submitLabel, pending, onSubmit, onCancel }) {
  const [value, setValue] = useState(initialValue);
  const [error, setError] = useState("");
  const textareaRef = useRef(null);

  // Ouvert par un clic : le curseur va dans le champ (jamais au montage de la page).
  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.focus();
    const end = node.value.length;
    node.setSelectionRange(end, end);
  }, []);

  const submit = () => {
    if (pending) return;
    if (!value.trim()) {
      setError("Écrivez une information avant d'enregistrer.");
      return;
    }
    setError("");
    onSubmit(value);
  };

  const length = value.length;
  const errorId = `${id}-error`;

  return (
    <form
      className="cz-note-form"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="cz-field-row">
        <label className="cz-label" htmlFor={id}>
          {label}
        </label>
        <span className={`cz-counter${length > NOTE_MAX_LENGTH ? " is-over" : ""}`} aria-live="off">
          {length}/{NOTE_MAX_LENGTH}
        </span>
      </div>
      <textarea
        ref={textareaRef}
        id={id}
        className="cz-textarea"
        value={value}
        maxLength={NOTE_MAX_LENGTH}
        onChange={(event) => {
          setValue(event.target.value);
          if (error) setError("");
        }}
        onKeyDown={(event) => {
          if (isSubmitShortcut(event)) {
            event.preventDefault();
            submit();
          }
        }}
        placeholder="Contexte, échanges avec le membre, éléments transmis…"
        aria-invalid={error ? "true" : undefined}
        aria-describedby={error ? errorId : undefined}
        disabled={pending}
      />
      {error && (
        <p className="cz-field-error" id={errorId} role="alert">
          {error}
        </p>
      )}
      <div className="cz-note-form-actions">
        <span className="cz-hint cz-keys-hint">Ctrl ou ⌘ + Entrée pour enregistrer</span>
        <button type="button" className="cz-button cz-button--compact" onClick={onCancel} disabled={pending}>
          Annuler
        </button>
        <button type="submit" className="cz-button cz-button--compact cz-button--primary" disabled={pending}>
          {pending && <Loader2 size={15} className="cz-spin" aria-hidden="true" />}
          {submitLabel}
        </button>
      </div>
    </form>
  );
}

// Informations complémentaires d'une sanction : ajout, modification et suppression (auteur ou Responsable).
export default function SanctionNotes({ casierId, sanction }) {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [toDelete, setToDelete] = useState(null);

  const notes = Array.isArray(sanction?.notes) ? sanction.notes : [];

  const applyDetail = (detail) => {
    if (detail) queryClient.setQueryData(casierKeys.detail(casierId), detail);
    queryClient.invalidateQueries({ queryKey: casierKeys.lists() });
  };

  const addMutation = useMutation({
    mutationFn: (content) => addNote(casierId, sanction.id, content),
    onSuccess: (detail) => {
      applyDetail(detail);
      setAdding(false);
      toast.success("Information ajoutée.");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const updateMutation = useMutation({
    mutationFn: ({ noteId, content }) => updateNote(casierId, sanction.id, noteId, content),
    onSuccess: (detail) => {
      applyDetail(detail);
      setEditingId(null);
      toast.success("Information modifiée.");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const deleteMutation = useMutation({
    mutationFn: (note) => deleteNote(casierId, sanction.id, note.id),
    onSuccess: (detail) => {
      applyDetail(detail);
      setToDelete(null);
      toast.success("Information supprimée.");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const saveEdit = (note, content) => {
    if (content.trim() === String(note.content || "").trim()) {
      setEditingId(null);
      return;
    }
    updateMutation.mutate({ noteId: note.id, content });
  };

  const isEmpty = notes.length === 0 && !adding;
  const titleId = `cz-notes-${sanction.id}`;

  return (
    <section
      className={`cz-sanction-section cz-notes${isEmpty ? " is-empty" : ""}`}
      aria-label={isEmpty ? "Informations complémentaires" : undefined}
      aria-labelledby={isEmpty ? undefined : titleId}
    >
      <div className="cz-section-head">
        {!isEmpty && (
          <h4 className="cz-section-title" id={titleId}>
            <MessageSquareText size={13} aria-hidden="true" />
            {notes.length > 0
              ? plural(notes.length, "information complémentaire", "informations complémentaires")
              : "Informations complémentaires"}
          </h4>
        )}
        {!adding && (
          <div className="cz-section-actions">
            <button
              type="button"
              className="cz-button cz-button--compact cz-button--subtle"
              onClick={() => setAdding(true)}
            >
              <MessageSquarePlus size={15} aria-hidden="true" />
              Ajouter une information
            </button>
          </div>
        )}
      </div>

      {notes.length > 0 && (
        <ul className="cz-notes-list">
          {notes.map((note) => {
            const editing = editingId === note.id;
            const editedByOther =
              note.updated_by && note.updated_by.id && note.updated_by.id !== note.created_by?.id;
            return (
              <li key={note.id} className="cz-note">
                <p className="cz-note-meta">
                  <strong>{authorName(note.created_by)}</strong>
                  <time dateTime={note.created_at || undefined}>{formatDate(note.created_at)}</time>
                  {note.updated_at && (
                    <span>
                      · modifiée le {formatDate(note.updated_at)}
                      {editedByOther ? ` par ${authorName(note.updated_by)}` : ""}
                    </span>
                  )}
                </p>

                {editing ? (
                  <NoteForm
                    id={`cz-note-edit-${note.id}`}
                    label="Modifier l'information"
                    initialValue={note.content || ""}
                    submitLabel="Enregistrer"
                    pending={updateMutation.isPending}
                    onSubmit={(content) => saveEdit(note, content)}
                    onCancel={() => setEditingId(null)}
                  />
                ) : (
                  <>
                    <p className="cz-note-text">{note.content}</p>
                    {note.can_edit && (
                      <div className="cz-note-actions">
                        <button
                          type="button"
                          className="cz-link"
                          onClick={() => {
                            setAdding(false);
                            setEditingId(note.id);
                          }}
                        >
                          Modifier
                          <span className="cz-sr-only"> l'information de {authorName(note.created_by)}</span>
                        </button>
                        <button type="button" className="cz-link cz-link--danger" onClick={() => setToDelete(note)}>
                          Supprimer
                          <span className="cz-sr-only"> l'information de {authorName(note.created_by)}</span>
                        </button>
                      </div>
                    )}
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {adding && (
        <NoteForm
          id={`cz-note-new-${sanction.id}`}
          label="Nouvelle information"
          submitLabel="Ajouter"
          pending={addMutation.isPending}
          onSubmit={(content) => addMutation.mutate(content)}
          onCancel={() => setAdding(false)}
        />
      )}

      <ConfirmDialog
        open={Boolean(toDelete)}
        title="Supprimer cette information ?"
        description="Elle disparaîtra du casier. La suppression est journalisée."
        confirmLabel="Supprimer"
        pending={deleteMutation.isPending}
        onConfirm={() => toDelete && deleteMutation.mutate(toDelete)}
        onCancel={() => setToDelete(null)}
      />
    </section>
  );
}
