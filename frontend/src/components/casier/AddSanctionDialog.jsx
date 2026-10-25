import "./casier-detail.css";

import { useId, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as RadioGroup from "@radix-ui/react-radio-group";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, CircleAlert, ExternalLink, EyeOff, Loader2, X } from "lucide-react";
import { toast } from "sonner";

import MemberAvatar from "./MemberAvatar";
import StatusPill from "./StatusPill";
import { addSanction, casierKeys, errorMessage, errorStatus } from "./casierApi";
import {
  DURATION_MAX_LENGTH,
  REASON_MAX_LENGTH,
  SANCTION_TYPES,
  durationPresetsFor,
  kindLabel,
  projectedStatus,
  statusMeta,
  typeHasDuration,
} from "./casierConstants";
import { formatDate, formatVerdict, memberHandle, memberName } from "./formatters";

const DEFAULT_TYPE = "avertissement";
// Ancienne valeur sans ambiguïté (API d'avant la refonte) : utile seulement pour l'aperçu du statut.
const LEGACY_STATUS = { bloque: "banni" };

function fold(text) {
  return String(text || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

// Type suggéré d'après la sanction proposée par l'IA : premier mot-clé rencontré dans le texte.
const TYPE_KEYWORDS = [
  { type: "rappel_a_lordre", pattern: /rappel/ },
  { type: "avertissement", pattern: /avertissement|averti/ },
  { type: "mute", pattern: /mute|timeout|time out|sourdine|exclusion temporaire/ },
  { type: "kick", pattern: /\bkick|expuls/ },
  { type: "bannissement", pattern: /\bban|bann/ },
];

function suggestedType(aiFlag) {
  const text = fold(aiFlag?.verdict?.sanction);
  if (!text) return DEFAULT_TYPE;
  let best = null;
  TYPE_KEYWORDS.forEach(({ type, pattern }) => {
    const match = pattern.exec(text);
    if (match && (best === null || match.index < best.index)) best = { type, index: match.index };
  });
  return best ? best.type : DEFAULT_TYPE;
}

function initialReason(aiFlag) {
  if (!aiFlag) return "";
  const reason = String(aiFlag.verdict?.raison || "").trim() || kindLabel(aiFlag.kind);
  return `[IA] ${reason}`.slice(0, REASON_MAX_LENGTH);
}

function safeExternalUrl(url) {
  return typeof url === "string" && /^https:\/\//i.test(url) ? url : null;
}

function FlagQuote({ aiFlag }) {
  const message = aiFlag.message || {};
  const verdict = formatVerdict(aiFlag.verdict);
  const jumpUrl = safeExternalUrl(message.jump_url);
  const channel = aiFlag.channel?.name ? `#${aiFlag.channel.name}` : "";

  return (
    <div className="cz-flag-quote">
      <p className="cz-flag-quote-title">
        <Bot size={15} aria-hidden="true" />
        Message signalé par l'IA
      </p>
      {message.content_redacted || !message.content ? (
        <p className="cz-flag-quote-redacted">
          <EyeOff size={15} aria-hidden="true" />
          {message.content_redacted
            ? "Contenu non conservé : le modèle a refusé d'analyser ce message, qui peut être sensible. Consultez-le sur Discord si nécessaire."
            : "Contenu du message indisponible."}
        </p>
      ) : (
        <blockquote>{message.content}</blockquote>
      )}
      <p className="cz-flag-quote-meta">
        {[channel, formatDate(message.created_at || aiFlag.created_at), verdict || kindLabel(aiFlag.kind)]
          .filter(Boolean)
          .join(" · ")}
        {jumpUrl && (
          <a href={jumpUrl} target="_blank" rel="noopener noreferrer">
            Voir sur Discord
            <ExternalLink size={12} aria-hidden="true" />
            <span className="cz-sr-only"> (nouvel onglet)</span>
          </a>
        )}
      </p>
    </div>
  );
}

// Formulaire monté à chaque ouverture : état neuf, motif pré-rempli depuis le signalement éventuel.
function AddSanctionForm({ casier, aiFlag, onClose, onSaved, onPendingChange }) {
  const queryClient = useQueryClient();
  const uid = useId();
  const [type, setType] = useState(() => (aiFlag ? suggestedType(aiFlag) : DEFAULT_TYPE));
  const [reason, setReason] = useState(() => initialReason(aiFlag));
  const [duration, setDuration] = useState("");
  const [reasonError, setReasonError] = useState("");
  const [apiError, setApiError] = useState("");

  const member = casier.member || {};
  const withDuration = typeHasDuration(type);
  const presets = durationPresetsFor(type);
  const currentStatus = LEGACY_STATUS[casier.status] || casier.status || "vierge";
  const current = statusMeta(currentStatus);
  const next = statusMeta(projectedStatus(currentStatus, type));

  const mutation = useMutation({
    mutationFn: (body) => addSanction(casier.id, body),
    onMutate: () => onPendingChange(true),
    onSettled: () => onPendingChange(false),
    onSuccess: (detail) => {
      if (detail) queryClient.setQueryData(casierKeys.detail(casier.id), detail);
      queryClient.invalidateQueries({ queryKey: casierKeys.lists() });
      if (aiFlag) queryClient.invalidateQueries({ queryKey: casierKeys.aiFlags() });
      toast.success("Sanction enregistrée.");
      onSaved?.(detail);
    },
    onError: (error) => {
      if (aiFlag && [404, 409, 422].includes(errorStatus(error))) {
        queryClient.invalidateQueries({ queryKey: casierKeys.aiFlags() });
      }
      setApiError(errorMessage(error));
    },
  });

  const pending = mutation.isPending;

  const submit = () => {
    if (pending) return;
    if (!reason.trim()) {
      setReasonError("Indiquez le motif de la sanction.");
      return;
    }
    setReasonError("");
    setApiError("");
    mutation.mutate({
      type,
      reason,
      duration: withDuration ? duration : undefined,
      ai_flag_id: aiFlag?.id || undefined,
    });
  };

  const typeLabelId = `${uid}-type`;
  const reasonId = `${uid}-reason`;
  const durationId = `${uid}-duration`;
  const reasonErrorId = `${uid}-reason-error`;
  const durationHintId = `${uid}-duration-hint`;
  const trimmedDuration = duration.trim().toLowerCase();

  return (
    <form
      className="cz-sanction-form"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="cz-dialog-body">
        <div className="cz-dialog-member">
          <MemberAvatar member={member} size={40} />
          <div className="cz-dialog-member-copy">
            <strong>{memberName(member)}</strong>
            {(memberHandle(member) || member.id) && (
              <span>{[memberHandle(member), member.id ? `ID ${member.id}` : ""].filter(Boolean).join(" · ")}</span>
            )}
          </div>
          <StatusPill status={currentStatus} size="sm" />
        </div>

        {aiFlag && <FlagQuote aiFlag={aiFlag} />}

        <div className="cz-field">
          <p className="cz-label" id={typeLabelId}>
            Type de sanction
          </p>
          <RadioGroup.Root
            className="cz-type-grid"
            value={type}
            onValueChange={(value) => value && setType(value)}
            aria-labelledby={typeLabelId}
            disabled={pending}
          >
            {SANCTION_TYPES.map((option) => {
              const Icon = option.icon;
              return (
                <RadioGroup.Item key={option.value} value={option.value} className="cz-type-option">
                  <span className={`cz-sanction-icon cz-sanction-icon--${option.tone}`} aria-hidden="true">
                    <Icon size={17} />
                  </span>
                  <span className="cz-type-option-copy">
                    {option.label}
                    {option.hint && <small>{option.hint}</small>}
                  </span>
                </RadioGroup.Item>
              );
            })}
          </RadioGroup.Root>
        </div>

        <div className="cz-field">
          <div className="cz-field-row">
            <label className="cz-label" htmlFor={reasonId}>
              Motif
            </label>
            <span className={`cz-counter${reason.length > REASON_MAX_LENGTH ? " is-over" : ""}`}>
              {reason.length}/{REASON_MAX_LENGTH}
            </span>
          </div>
          <textarea
            id={reasonId}
            className="cz-textarea"
            value={reason}
            maxLength={REASON_MAX_LENGTH}
            onChange={(event) => {
              setReason(event.target.value);
              if (reasonError) setReasonError("");
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                submit();
              }
            }}
            placeholder="Ce qui s'est passé, où, et la règle concernée."
            aria-invalid={reasonError ? "true" : undefined}
            aria-describedby={reasonError ? reasonErrorId : undefined}
            disabled={pending}
            aria-required="true"
          />
          {reasonError && (
            <p className="cz-field-error" id={reasonErrorId} role="alert">
              {reasonError}
            </p>
          )}
        </div>

        {withDuration && (
          <div className="cz-field">
            <label className="cz-label" htmlFor={durationId}>
              Durée
            </label>
            <div className="cz-chips cz-duration-presets" role="group" aria-label="Durées courantes">
              {presets.map((preset) => (
                <button
                  key={preset.value}
                  type="button"
                  className="cz-chip"
                  aria-pressed={trimmedDuration === preset.value.toLowerCase()}
                  onClick={() => setDuration(preset.value)}
                  disabled={pending}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            <input
              id={durationId}
              className="cz-input"
              type="text"
              value={duration}
              maxLength={DURATION_MAX_LENGTH}
              onChange={(event) => setDuration(event.target.value)}
              placeholder="Ex. 1h30, 3 jours"
              aria-describedby={durationHintId}
              autoComplete="off"
              disabled={pending}
            />
            <p className="cz-hint" id={durationHintId}>
              Facultatif. Laissez vide si la durée est inconnue.
            </p>
          </div>
        )}

        <p className="cz-status-preview" aria-live="polite">
          Statut après enregistrement :
          <StatusPill status={next.value} size="sm">
            {next.label}
          </StatusPill>
          {next.value === current.value ? (
            <span>(inchangé)</span>
          ) : (
            <span>
              (actuellement : <strong>{current.label}</strong>)
            </span>
          )}
        </p>

        {apiError && (
          <p className="cz-dialog-error" role="alert">
            <CircleAlert size={16} aria-hidden="true" />
            {apiError}
          </p>
        )}
      </div>

      <div className="cz-dialog-footer">
        <p className="cz-dialog-footer-note cz-keys-hint">Ctrl ou ⌘ + Entrée pour enregistrer</p>
        <button type="button" className="cz-button" onClick={onClose} disabled={pending}>
          Annuler
        </button>
        <button type="submit" className="cz-button cz-button--primary" disabled={pending} aria-busy={pending || undefined}>
          {pending && <Loader2 size={16} className="cz-spin" aria-hidden="true" />}
          Enregistrer la sanction
        </button>
      </div>
    </form>
  );
}

// Le parent ferme la modale (open=false) dans onSaved ; fermeture bloquée pendant l'envoi.
export default function AddSanctionDialog({ open, casier, aiFlag = null, onClose, onSaved }) {
  const [pending, setPending] = useState(false);
  const contentRef = useRef(null);
  const isOpen = Boolean(open && casier?.id);

  const requestClose = () => {
    if (!pending) onClose?.();
  };

  return (
    <Dialog.Root
      open={isOpen}
      onOpenChange={(next) => {
        if (!next) requestClose();
      }}
    >
      <Dialog.Portal>
        <div className="cz-dialog-root">
          <Dialog.Overlay className="cz-dialog-overlay" />
          <Dialog.Content
            ref={contentRef}
            className="cz-dialog cz-sanction-dialog"
            aria-describedby={undefined}
            onOpenAutoFocus={(event) => {
              // Le focus va sur le type sélectionné plutôt que sur la croix.
              const checked = contentRef.current?.querySelector('[role="radio"][data-state="checked"]');
              if (checked) {
                event.preventDefault();
                checked.focus();
              }
            }}
          >
            <div className="cz-dialog-header">
              <div>
                <p className="cz-dialog-eyebrow">{aiFlag ? "Depuis un signalement IA" : "Casier"}</p>
                <Dialog.Title className="cz-dialog-title">Ajouter une sanction</Dialog.Title>
              </div>
              <button type="button" className="cz-dialog-close" onClick={requestClose} disabled={pending} aria-label="Fermer">
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            {isOpen && (
              <AddSanctionForm
                casier={casier}
                aiFlag={aiFlag}
                onClose={requestClose}
                onSaved={onSaved}
                onPendingChange={setPending}
              />
            )}
          </Dialog.Content>
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
