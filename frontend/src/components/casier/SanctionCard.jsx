import "./casier-detail.css";

import { Link } from "react-router-dom";
import { Bot, ExternalLink } from "lucide-react";

import AttachmentGallery from "./AttachmentGallery";
import SanctionNotes from "./SanctionNotes";
import StatusPill from "./StatusPill";
import { ORIGIN_LABELS, REMINDER_TYPE, sanctionTypeMeta } from "./casierConstants";
import { casierLink, formatDate, formatUntil, sanctionAuthorLabel, sanctionOrigin } from "./formatters";

function isFuture(value) {
  const time = Date.parse(value || "");
  return Number.isFinite(time) && time > Date.now();
}

function safeExternalUrl(url) {
  return typeof url === "string" && /^https:\/\//i.test(url) ? url : null;
}

// Une sanction de l'historique : motif, auteur, origine, durée, fichiers et informations complémentaires.
export default function SanctionCard({ casierId, sanction, highlighted = false, onFilesQueued, copyStalled = false }) {
  const meta = sanctionTypeMeta(sanction.type);
  const Icon = meta.icon;
  const origin = sanctionOrigin(sanction);
  const logUrl = origin === "discord_log" ? safeExternalUrl(sanction.source?.message_url) : null;
  const active = Boolean(sanction.is_active) && (!sanction.expires_at || isFuture(sanction.expires_at));
  const until = sanction.expires_at ? formatUntil(sanction.expires_at) : "";
  const durationLabel = sanction.duration
    ? /^permanent/i.test(String(sanction.duration).trim())
      ? "Permanent"
      : `Durée ${sanction.duration}`
    : "";
  const titleId = `sanction-${sanction.id}-title`;

  return (
    <article
      id={`sanction-${sanction.id}`}
      className={`cz-sanction${highlighted ? " cz-target" : ""}`}
      aria-labelledby={titleId}
    >
      <header className="cz-sanction-head">
        <span className={`cz-sanction-icon cz-sanction-icon--${meta.tone}`} aria-hidden="true">
          <Icon size={19} />
        </span>
        <div className="cz-sanction-title">
          <h3 id={titleId}>
            <StatusPill variant={meta.tone}>{meta.label}</StatusPill>
          </h3>
        </div>
        <time className="cz-sanction-date" dateTime={sanction.created_at || undefined}>
          {formatDate(sanction.created_at)}
        </time>
      </header>

      {sanction.type === REMINDER_TYPE && (
        <p className="cz-sanction-hint">Rappel à l'ordre : sans effet sur le statut.</p>
      )}

      {sanction.reason ? (
        <p className="cz-sanction-reason">{sanction.reason}</p>
      ) : (
        <p className="cz-sanction-reason cz-meta">Aucun motif renseigné.</p>
      )}

      <ul className="cz-sanction-meta">
        <li>{sanctionAuthorLabel(sanction)}</li>
        <li>
          {logUrl ? (
            <a href={logUrl} target="_blank" rel="noopener noreferrer">
              {ORIGIN_LABELS.discord_log}
              <ExternalLink size={12} aria-hidden="true" />
              <span className="cz-sr-only"> (nouvel onglet)</span>
            </a>
          ) : (
            ORIGIN_LABELS[origin] || ORIGIN_LABELS.manual
          )}
        </li>
        {durationLabel && <li>{durationLabel}</li>}
        {until && <li>{until}</li>}
        {active && (
          <li>
            <strong className="cz-sanction-active">En cours</strong>
          </li>
        )}
        {sanction.ai_flag_id && (
          <li>
            <Link
              to={casierLink({ casierId, onglet: "signalements", signalementId: sanction.ai_flag_id })}
              title="Ouvrir le signalement de l'IA à l'origine de cette sanction"
            >
              <Bot size={13} aria-hidden="true" />
              Signalement IA
            </Link>
          </li>
        )}
      </ul>

      <div className="cz-sanction-extras">
        <AttachmentGallery
          casierId={casierId}
          sanction={sanction}
          onFilesQueued={onFilesQueued}
          copyStalled={copyStalled}
        />
        <SanctionNotes casierId={casierId} sanction={sanction} />
      </div>
    </article>
  );
}
