import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import * as Popover from "@radix-ui/react-popover";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowUpRight,
  CircleSlash,
  ExternalLink,
  EyeOff,
  FolderOpen,
  Gavel,
  Loader2,
  MessageSquareText,
  ThumbsUp,
  UserPlus,
} from "lucide-react";

import "./casier-fiches-ia.css";
import MemberAvatar from "./MemberAvatar";
import StatusPill from "./StatusPill";
import { casierKeys, errorMessage, reviewAiFlag } from "./casierApi";
import {
  MODE_LABELS,
  PLANNED_ACTION_LABELS,
  REVIEW_COMMENT_MAX_LENGTH,
  gravityTone,
  kindLabel,
  reviewMeta,
} from "./casierConstants";
import {
  authorName,
  casierLink,
  formatDate,
  formatExecutedAction,
  formatRelative,
  formatVerdict,
  memberHandle,
  memberName,
} from "./formatters";

const LINKED_FALSE_POSITIVE =
  "Ce signalement est lié à une sanction : il ne peut pas être classé faux positif.";

// Laisse le temps de cliquer « Annuler » (la carte quitte souvent la liste filtrée).
const UNDO_TOAST_DURATION_MS = 8000;

const REVIEW_TOASTS = {
  a_traiter: "Signalement remis à traiter.",
  pertinent: "Signalement marqué pertinent.",
  faux_positif: "Signalement classé faux positif.",
};

function safeExternalUrl(url) {
  return typeof url === "string" && /^https:\/\//i.test(url) ? url : null;
}

// Remplace un signalement dans toutes les formes de cache : pages (liste), { items } (compteur), item seul.
export function patchFlagInCache(data, updated) {
  if (!data || !updated?.id) return data;
  if (Array.isArray(data.pages)) {
    return { ...data, pages: data.pages.map((page) => patchFlagInCache(page, updated)) };
  }
  if (Array.isArray(data.items)) {
    let changed = false;
    const items = data.items.map((item) => {
      if (item?.id !== updated.id) return item;
      changed = true;
      return { ...item, ...updated };
    });
    return changed ? { ...data, items } : data;
  }
  if (data.id === updated.id) return { ...data, ...updated };
  return data;
}

// Indépendant du cycle de vie de la carte : la carte peut disparaître de la liste filtrée juste après.
async function applyReview(queryClient, flag, body) {
  const updated = await reviewAiFlag(flag.id, body);
  if (updated?.id) {
    queryClient.setQueriesData({ queryKey: casierKeys.aiFlags() }, (old) => patchFlagInCache(old, updated));
  }
  queryClient.invalidateQueries({ queryKey: casierKeys.aiFlags() });
  queryClient.invalidateQueries({ queryKey: casierKeys.lists() });
  const casierId = updated?.casier_id || flag.casier_id;
  if (casierId) queryClient.invalidateQueries({ queryKey: casierKeys.detail(casierId) });
  return updated || flag;
}

function isPlainClick(event) {
  return !event.defaultPrevented && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

function DeepLink({ to, params, onNavigate, className, children }) {
  return (
    <Link
      to={to}
      className={className}
      onClick={(event) => {
        if (!onNavigate || !isPlainClick(event)) return;
        event.preventDefault();
        onNavigate(params);
      }}
    >
      {children}
    </Link>
  );
}

function MessageQuote({ text }) {
  const ref = useRef(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node || expanded) return;
    setOverflows(node.scrollHeight > node.clientHeight + 1);
  }, [text, expanded]);

  return (
    <div className="cz-flag-message">
      <blockquote ref={ref} className={`cz-flag-text${expanded ? "" : " is-clamped"}`}>
        {text}
      </blockquote>
      {(overflows || expanded) && (
        <button
          type="button"
          className="cz-link cz-flag-more"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Réduire" : "Afficher tout"}
        </button>
      )}
    </div>
  );
}

function CommentPopover({ flag, disabled, onSave, saving }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const fieldId = useId();
  const current = flag.review?.comment || "";

  useEffect(() => {
    if (open) setValue(current);
  }, [open, current]);

  const save = async (nextComment) => {
    const ok = await onSave(nextComment);
    if (ok) setOpen(false);
  };

  const over = value.length > REVIEW_COMMENT_MAX_LENGTH;

  return (
    <Popover.Root open={open} onOpenChange={(next) => !saving && setOpen(next)}>
      <Popover.Trigger asChild>
        <button type="button" className="cz-button cz-button--compact" disabled={disabled}>
          <MessageSquareText size={15} aria-hidden="true" />
          {current ? "Modifier le commentaire" : "Commenter"}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <div className="cz-dialog-root">
          <Popover.Content className="cz-popover cz-flag-comment-form" sideOffset={8} align="start" collisionPadding={16}>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (!over) save(value);
              }}
            >
              <div className="cz-field">
                <div className="cz-field-row">
                  <label className="cz-label" htmlFor={fieldId}>
                    Commentaire de revue
                  </label>
                  <span className={`cz-counter${over ? " is-over" : ""}`}>
                    {value.length}/{REVIEW_COMMENT_MAX_LENGTH}
                  </span>
                </div>
                <textarea
                  id={fieldId}
                  className="cz-textarea"
                  rows={4}
                  value={value}
                  maxLength={REVIEW_COMMENT_MAX_LENGTH}
                  placeholder="Contexte, décision, lien avec un autre signalement…"
                  onChange={(event) => setValue(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                      event.preventDefault();
                      if (!over) save(value);
                    }
                  }}
                  aria-invalid={over || undefined}
                />
              </div>
              <div className="cz-flag-comment-actions">
                {current && (
                  <button
                    type="button"
                    className="cz-button cz-button--compact cz-button--subtle"
                    onClick={() => save("")}
                    disabled={saving}
                  >
                    Effacer
                  </button>
                )}
                <Popover.Close asChild>
                  <button type="button" className="cz-button cz-button--compact" disabled={saving}>
                    Annuler
                  </button>
                </Popover.Close>
                <button
                  type="submit"
                  className="cz-button cz-button--compact cz-button--primary"
                  disabled={saving || over || value.trim() === current.trim()}
                >
                  {saving && <Loader2 size={15} className="cz-spin" aria-hidden="true" />}
                  Enregistrer
                </button>
              </div>
            </form>
          </Popover.Content>
        </div>
      </Popover.Portal>
    </Popover.Root>
  );
}

// Carte d'un signalement IA (vue globale et onglet du casier). Pas d'attribut `id` : la même carte peut
// être montée deux fois (vue globale et onglet), le ciblage passe par `data-flag-id` sur l'élément parent.
export default function AiFlagCard({
  flag,
  compact = false,
  highlighted = false,
  onNavigate,
  onSanction,
  onCreateCasier,
}) {
  const queryClient = useQueryClient();
  const headingId = useId();
  const falsePositiveHintId = useId();
  const [pending, setPending] = useState(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const author = flag.author || { id: flag.discord_id };
  const review = flag.review || {};
  const status = reviewMeta(review.status).value;
  const verdict = flag.verdict || null;
  const gravity = Number(verdict?.gravite) || 0;
  const tone = gravityTone(gravity);
  const linked = Boolean(flag.sanction);
  const message = flag.message || {};
  const executed = Array.isArray(flag.executed) ? flag.executed.filter(Boolean) : [];
  const jumpUrl = safeExternalUrl(message.jump_url);
  const alertUrl = safeExternalUrl(flag.alert?.jump_url);
  const casierId = flag.casier_id || null;
  const verdictText = formatVerdict(verdict);
  const busy = Boolean(pending);

  const run = async (kind, body, { successMessage, undo } = {}) => {
    if (busy) return false;
    setPending(kind);
    try {
      await applyReview(queryClient, flag, body);
      if (successMessage) {
        toast.success(
          successMessage,
          undo ? { duration: UNDO_TOAST_DURATION_MS, action: { label: "Annuler", onClick: undo } } : undefined
        );
      }
      return true;
    } catch (error) {
      toast.error(errorMessage(error));
      return false;
    } finally {
      if (mountedRef.current) setPending(null);
    }
  };

  const setReview = (next) => {
    const previous = status;
    const target = previous === next ? "a_traiter" : next;
    if (target === "faux_positif" && linked) {
      toast.error(LINKED_FALSE_POSITIVE);
      return;
    }
    run(next, { review_status: target }, {
      successMessage: REVIEW_TOASTS[target],
      undo: () => {
        applyReview(queryClient, flag, { review_status: previous })
          .then(() => toast.success("Revue annulée."))
          .catch((error) => toast.error(errorMessage(error)));
      },
    });
  };

  const saveComment = (comment) =>
    run("comment", { review_status: status, comment }, {
      successMessage: comment.trim() ? "Commentaire enregistré." : "Commentaire effacé.",
    });

  const name = memberName(author);
  const handle = author.username && author.username !== name ? memberHandle(author) : "";
  const channelName = flag.channel?.name;
  const createdTitle = formatDate(flag.created_at);
  const canSanction = !linked && status !== "faux_positif";
  const falsePositiveBlocked = linked && status !== "faux_positif";
  const reviewer = review.reviewed_by;

  return (
    <article
      className={`cz-flag-card cz-flag-card--${tone}${highlighted ? " cz-target" : ""}`}
      aria-labelledby={headingId}
    >
      <header className="cz-flag-head">
        {!compact && <MemberAvatar member={author} size={40} />}
        <div className="cz-flag-who">
          {compact ? (
            <h3 id={headingId} className="cz-sr-only">
              Signalement du {createdTitle}
            </h3>
          ) : (
            <div className="cz-flag-name-row">
              <h3 id={headingId} className="cz-flag-name">
                {name}
              </h3>
              {handle && <span className="cz-meta">{handle}</span>}
              {flag.casier_status && <StatusPill status={flag.casier_status} size="sm" />}
            </div>
          )}
          <p className="cz-flag-where">
            <span className="cz-flag-channel">#{channelName || "salon inconnu"}</span>
            <span aria-hidden="true">·</span>
            <time dateTime={flag.created_at || undefined} title={createdTitle}>
              {formatRelative(flag.created_at)}
            </time>
          </p>
        </div>
        <div className="cz-flag-badges">
          {gravity > 0 ? (
            <StatusPill variant={tone} size="sm">
              Gravité {gravity}/3
            </StatusPill>
          ) : (
            <StatusPill variant="ia-0" size="sm">
              {kindLabel(flag.kind)}
            </StatusPill>
          )}
          <StatusPill variant={reviewMeta(status).tone} size="sm" />
        </div>
      </header>

      {message.content_redacted ? (
        <div className="cz-callout cz-flag-redacted">
          <EyeOff size={17} aria-hidden="true" />
          <p>
            Contenu non conservé : le modèle a refusé d'analyser ce message, qui peut être sensible. Consultez-le sur
            Discord si nécessaire.
          </p>
        </div>
      ) : message.content ? (
        <MessageQuote text={message.content} />
      ) : (
        <p className="cz-flag-missing">Contenu du message indisponible.</p>
      )}

      <div className="cz-flag-analysis">
        {verdictText ? (
          <p className="cz-flag-verdict">{verdictText}</p>
        ) : (
          <p className="cz-flag-verdict">
            {kindLabel(flag.kind)}
            {flag.kind === "illisible" && " : la réponse du modèle n'a pas pu être lue."}
            {flag.kind === "refus" && " : le modèle n'a pas rendu de verdict."}
          </p>
        )}
        {(verdict?.raison || verdict?.sanction) && (
          <dl className="cz-flag-facts">
            {verdict?.raison && (
              <>
                <dt>Raison</dt>
                <dd>{verdict.raison}</dd>
              </>
            )}
            {verdict?.sanction && (
              <>
                <dt>Sanction suggérée</dt>
                <dd>{verdict.sanction}</dd>
              </>
            )}
          </dl>
        )}
        {executed.length > 0 && (
          <div className="cz-flag-executed">
            <span className="cz-meta">Actions exécutées :</span>
            {executed.map((action, index) => (
              <StatusPill key={`${action}-${index}`} variant="ia" size="sm">
                {formatExecutedAction(action)}
              </StatusPill>
            ))}
          </div>
        )}
        <p className="cz-meta cz-flag-mode">
          {[
            MODE_LABELS[flag.mode],
            flag.planned_action ? `Action prévue : ${PLANNED_ACTION_LABELS[flag.planned_action] || flag.planned_action}` : null,
            flag.alert?.posted ? "Alerte publiée pour le staff" : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </div>

      {(reviewer || review.comment) && (
        <div className="cz-flag-review">
          {reviewer && (
            <p className="cz-meta">
              {reviewMeta(status).label} · revu par {authorName(reviewer)}
              {review.reviewed_at ? ` · ${formatDate(review.reviewed_at)}` : ""}
            </p>
          )}
          {review.comment && <p className="cz-flag-comment">{review.comment}</p>}
        </div>
      )}

      <div className="cz-flag-actions">
        <div className="cz-flag-toggles" role="group" aria-label="Revue du signalement">
          <button
            type="button"
            className="cz-chip cz-flag-toggle cz-flag-toggle--pertinent"
            aria-pressed={status === "pertinent"}
            onClick={() => setReview("pertinent")}
            disabled={busy}
            title={status === "pertinent" ? "Cliquer pour remettre « À traiter »" : undefined}
          >
            {pending === "pertinent" ? (
              <Loader2 size={14} className="cz-spin" aria-hidden="true" />
            ) : (
              <ThumbsUp size={14} aria-hidden="true" />
            )}
            Pertinent
          </button>
          <button
            type="button"
            className="cz-chip cz-flag-toggle cz-flag-toggle--faux"
            aria-pressed={status === "faux_positif"}
            aria-disabled={falsePositiveBlocked || undefined}
            aria-describedby={falsePositiveBlocked ? falsePositiveHintId : undefined}
            onClick={() => (falsePositiveBlocked ? toast.error(LINKED_FALSE_POSITIVE) : setReview("faux_positif"))}
            disabled={busy}
            title={
              falsePositiveBlocked
                ? LINKED_FALSE_POSITIVE
                : status === "faux_positif"
                  ? "Cliquer pour remettre « À traiter »"
                  : undefined
            }
          >
            {pending === "faux_positif" ? (
              <Loader2 size={14} className="cz-spin" aria-hidden="true" />
            ) : (
              <CircleSlash size={14} aria-hidden="true" />
            )}
            Faux positif
          </button>
          {falsePositiveBlocked && (
            <span id={falsePositiveHintId} className="cz-sr-only">
              {LINKED_FALSE_POSITIVE}
            </span>
          )}
        </div>

        <CommentPopover flag={flag} disabled={busy && pending !== "comment"} onSave={saveComment} saving={pending === "comment"} />

        <span className="cz-flag-actions-spacer" aria-hidden="true" />

        {canSanction && onSanction && (
          <button type="button" className="cz-button cz-button--compact cz-button--primary" onClick={() => onSanction(flag)}>
            <Gavel size={15} aria-hidden="true" />
            Sanctionner
          </button>
        )}

        {linked && flag.sanction?.casier_id && (
          <DeepLink
            to={casierLink({ casierId: flag.sanction.casier_id, sanctionId: flag.sanction.sanction_id })}
            params={{ casier: flag.sanction.casier_id, sanction: flag.sanction.sanction_id }}
            onNavigate={onNavigate}
            className="cz-button cz-button--compact"
          >
            <ArrowUpRight size={15} aria-hidden="true" />
            Voir la sanction
          </DeepLink>
        )}

        {casierId && !compact && (
          <DeepLink
            to={casierLink({ casierId })}
            params={{ casier: casierId }}
            onNavigate={onNavigate}
            className="cz-button cz-button--compact"
          >
            <FolderOpen size={15} aria-hidden="true" />
            Ouvrir le casier
          </DeepLink>
        )}

        {!casierId && onCreateCasier && (
          <button type="button" className="cz-button cz-button--compact" onClick={() => onCreateCasier(flag)}>
            <UserPlus size={15} aria-hidden="true" />
            Créer le casier
          </button>
        )}

        {jumpUrl && (
          <a
            href={jumpUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="cz-button cz-button--compact cz-button--subtle"
            aria-label="Voir le message sur Discord (nouvel onglet)"
          >
            <ExternalLink size={15} aria-hidden="true" />
            Voir sur Discord
          </a>
        )}

        {alertUrl && (
          <a
            href={alertUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="cz-button cz-button--compact cz-button--subtle"
            aria-label="Voir l'alerte du staff sur Discord (nouvel onglet)"
          >
            <ExternalLink size={15} aria-hidden="true" />
            Alerte
          </a>
        )}
      </div>
    </article>
  );
}
