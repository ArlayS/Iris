import "./casier-detail.css";

import { useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, ImageOff, Loader2, Paperclip, RefreshCw, TriangleAlert, Upload, X } from "lucide-react";
import { toast } from "sonner";

import AttachmentLightbox from "./AttachmentLightbox";
import ConfirmDialog from "./ConfirmDialog";
import { casierKeys, deleteAttachment, errorMessage, resyncAttachments, uploadAttachment } from "./casierApi";
import {
  ATTACHMENT_STATUS_META,
  MAX_ATTACHMENTS_PER_SANCTION,
  UPLOAD_ACCEPT,
  UPLOAD_EXTENSIONS,
  UPLOAD_MAX_BYTES,
} from "./casierConstants";
import { attachmentHref, authorName, formatBytes, plural, sanctionOrigin } from "./formatters";

const FORMAT_ERROR = "Format non autorisé (images, PDF ou TXT).";

function extensionOf(name) {
  const match = /\.([A-Za-z0-9]+)$/.exec(String(name || ""));
  return match ? match[1].toLowerCase() : "";
}

function isCanceled(error) {
  return error?.name === "CanceledError" || error?.name === "AbortError" || error?.code === "ERR_CANCELED";
}

function originLabel(attachment) {
  if (attachment.origin === "upload") return `Ajouté par ${authorName(attachment.uploaded_by)}`;
  return "Log Discord";
}

function AttachmentTile({ attachment, onOpen, onRemove, removing }) {
  const [thumbFailed, setThumbFailed] = useState(false);
  const status = attachment.status || "stored";
  const href = status === "stored" ? attachmentHref(attachment.download_url) : null;
  const downloadHref = status === "stored" ? attachmentHref(attachment.download_url, true) : null;
  const name = attachment.filename || "Fichier";
  const size = formatBytes(attachment.size);
  const statusMeta = ATTACHMENT_STATUS_META[status];
  const showThumb = Boolean(attachment.inline && href && !thumbFailed);

  let visual;
  if (showThumb) {
    visual = (
      <button type="button" className="cz-file-thumb" onClick={onOpen} aria-label={`Agrandir l'image ${name}`}>
        <img src={href} alt={name} loading="lazy" decoding="async" onError={() => setThumbFailed(true)} />
      </button>
    );
  } else if (status === "pending") {
    visual = (
      <div className="cz-file-visual cz-file-visual--pending">
        <Loader2 size={22} className="cz-spin" aria-hidden="true" />
        <span>{statusMeta.label}</span>
      </div>
    );
  } else if (status === "failed" || status === "too_large") {
    visual = (
      <div className={`cz-file-visual cz-file-visual--${status}`}>
        <TriangleAlert size={22} aria-hidden="true" />
        <span>{statusMeta.label}</span>
      </div>
    );
  } else {
    visual = (
      <div className="cz-file-visual">
        {attachment.inline ? <ImageOff size={24} aria-hidden="true" /> : <FileText size={24} aria-hidden="true" />}
        <span>{extensionOf(name).toUpperCase() || "Fichier"}</span>
      </div>
    );
  }

  return (
    <li className="cz-file">
      {visual}
      <div className="cz-file-body">
        <p className="cz-file-name" title={name}>
          {name}
        </p>
        <p className="cz-file-info">{[size, originLabel(attachment)].filter(Boolean).join(" · ")}</p>
        {(status === "failed" || status === "too_large") && attachment.error && (
          <p className="cz-file-error">{attachment.error}</p>
        )}
        {(downloadHref || attachment.can_delete) && (
          <div className="cz-file-actions">
            {downloadHref && (
              <a className="cz-link" href={downloadHref} download={name}>
                Télécharger
                <span className="cz-sr-only"> {name}</span>
              </a>
            )}
            {attachment.can_delete && (
              <button type="button" className="cz-link cz-link--danger" onClick={onRemove} disabled={removing}>
                Retirer
                <span className="cz-sr-only"> {name}</span>
              </button>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

// Fichiers d'une sanction : copies des logs Discord, ajouts à la main, visionneuse.
// `copyStalled` : le détail ne sonde plus alors que des copies restent en attente (relance permise).
export default function AttachmentGallery({ casierId, sanction, onFilesQueued, copyStalled = false }) {
  const queryClient = useQueryClient();
  const inputRef = useRef(null);
  const abortRef = useRef(null);
  const [progress, setProgress] = useState(null);
  const [uploadName, setUploadName] = useState("");
  const [lightboxIndex, setLightboxIndex] = useState(null);
  const [toRemove, setToRemove] = useState(null);

  const attachments = useMemo(
    () => (Array.isArray(sanction?.attachments) ? sanction.attachments : []),
    [sanction?.attachments]
  );
  const images = useMemo(
    () => attachments.filter((item) => item.status === "stored" && item.inline && attachmentHref(item.download_url)),
    [attachments]
  );
  const pendingCount = attachments.filter((item) => item.status === "pending").length;
  const hasFailed = attachments.some((item) => item.status === "failed");
  const fromLog = sanctionOrigin(sanction) === "discord_log";
  const limitReached = attachments.length >= MAX_ATTACHMENTS_PER_SANCTION;
  const copyRunning = pendingCount > 0 && !copyStalled;

  const applyDetail = (detail) => {
    if (detail) queryClient.setQueryData(casierKeys.detail(casierId), detail);
    queryClient.invalidateQueries({ queryKey: casierKeys.lists() });
  };

  const uploadMutation = useMutation({
    mutationFn: ({ file, signal }) =>
      uploadAttachment(casierId, sanction.id, file, (percent) => setProgress(percent), { signal }),
    onSuccess: (detail) => {
      applyDetail(detail);
      toast.success("Fichier ajouté.");
    },
    onError: (error) => {
      if (isCanceled(error)) {
        toast("Envoi annulé.");
        return;
      }
      toast.error(errorMessage(error));
    },
    onSettled: () => {
      abortRef.current = null;
      setProgress(null);
      setUploadName("");
    },
  });

  const resyncMutation = useMutation({
    mutationFn: () => resyncAttachments(casierId, sanction.id),
    onSuccess: (detail) => {
      onFilesQueued?.();
      applyDetail(detail);
      toast.success("Récupération des fichiers lancée.");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const removeMutation = useMutation({
    mutationFn: (attachment) => deleteAttachment(casierId, sanction.id, attachment.id),
    onSuccess: (detail) => {
      applyDetail(detail);
      setToRemove(null);
      toast.success("Fichier retiré.");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const uploading = uploadMutation.isPending;

  const handleFile = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || uploading) return;
    if (!UPLOAD_EXTENSIONS.includes(extensionOf(file.name))) {
      toast.error(FORMAT_ERROR);
      return;
    }
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    abortRef.current = controller;
    setUploadName(file.name);
    setProgress(0);
    uploadMutation.mutate({ file, signal: controller?.signal });
  };

  const cancelUpload = () => {
    abortRef.current?.abort();
  };

  const openPicker = () => {
    if (!uploading && !limitReached) inputRef.current?.click();
  };

  const openImage = (attachment) => {
    const index = images.findIndex((item) => item.id === attachment.id);
    if (index >= 0) setLightboxIndex(index);
  };

  // Mis en avant quand le log a sûrement quelque chose à apporter (aucun fichier, échec, modérateur inconnu).
  const emphasizeResync = attachments.length === 0 || hasFailed || !sanction?.moderator;
  const isEmpty = attachments.length === 0 && !uploading;
  const percent = typeof progress === "number" ? progress : null;

  return (
    <section
      className={`cz-sanction-section cz-files${isEmpty ? " is-empty" : ""}`}
      aria-label={isEmpty ? "Fichiers" : undefined}
      aria-labelledby={isEmpty ? undefined : `cz-files-${sanction.id}`}
    >
      <div className="cz-section-head">
        {!isEmpty && (
          <h4 className="cz-section-title" id={`cz-files-${sanction.id}`}>
            <Paperclip size={13} aria-hidden="true" />
            {plural(attachments.length, "fichier")}
          </h4>
        )}

        <div className="cz-section-actions">
          <input
            ref={inputRef}
            type="file"
            className="cz-file-input"
            accept={UPLOAD_ACCEPT}
            onChange={handleFile}
            tabIndex={-1}
            aria-hidden="true"
          />
          <button
            type="button"
            className="cz-button cz-button--compact cz-button--subtle"
            onClick={openPicker}
            disabled={uploading || limitReached}
            title={
              limitReached
                ? `Limite de ${MAX_ATTACHMENTS_PER_SANCTION} fichiers atteinte pour cette sanction.`
                : `Images, PDF ou TXT, ${formatBytes(UPLOAD_MAX_BYTES)} maximum.`
            }
          >
            <Upload size={15} aria-hidden="true" />
            Ajouter un fichier
          </button>

          {fromLog && (
            <button
              type="button"
              className={`cz-button cz-button--compact${emphasizeResync ? "" : " cz-button--subtle"}`}
              onClick={() => resyncMutation.mutate()}
              disabled={copyRunning || resyncMutation.isPending}
              title="Relire le message de log OasisBot pour copier ses fichiers dans Iris."
            >
              {copyRunning || resyncMutation.isPending ? (
                <Loader2 size={15} className="cz-spin" aria-hidden="true" />
              ) : (
                <RefreshCw size={15} aria-hidden="true" />
              )}
              {copyRunning
                ? "Copie en cours…"
                : resyncMutation.isPending
                  ? "Récupération…"
                  : "Récupérer les fichiers du log"}
            </button>
          )}
        </div>
      </div>

      {pendingCount > 0 && copyStalled && (
        <p className="cz-hint">
          La copie prend plus de temps que prévu. Rechargez la page pour vérifier
          {fromLog ? ", ou relancez la récupération dans quelques minutes." : "."}
        </p>
      )}

      {uploading && (
        <div className="cz-upload">
          <span className="cz-upload-name" title={uploadName}>
            {uploadName}
          </span>
          <span
            className={`cz-progress${percent === null ? " cz-progress--indeterminate" : ""}`}
            role="progressbar"
            aria-label={`Envoi de ${uploadName}`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent ?? undefined}
          >
            <span className="cz-progress-bar" style={percent === null ? undefined : { width: `${percent}%` }} />
          </span>
          <span aria-hidden="true">{percent === null ? "Envoi…" : `${percent} %`}</span>
          <button type="button" className="cz-link" onClick={cancelUpload}>
            <X size={13} aria-hidden="true" />
            Annuler
          </button>
        </div>
      )}

      {attachments.length > 0 && (
        <ul className="cz-files-grid">
          {attachments.map((attachment) => (
            <AttachmentTile
              key={attachment.id}
              attachment={attachment}
              onOpen={() => openImage(attachment)}
              onRemove={() => setToRemove(attachment)}
              removing={removeMutation.isPending && removeMutation.variables?.id === attachment.id}
            />
          ))}
        </ul>
      )}

      <p className="cz-sr-only" aria-live="polite">
        {pendingCount > 0 ? `${plural(pendingCount, "copie")} de fichier en cours.` : ""}
      </p>

      <AttachmentLightbox
        attachments={images}
        index={lightboxIndex}
        onIndexChange={setLightboxIndex}
        onClose={() => setLightboxIndex(null)}
      />

      <ConfirmDialog
        open={Boolean(toRemove)}
        title="Retirer ce fichier ?"
        description={
          toRemove
            ? `« ${toRemove.filename || "Fichier"} » sera retiré de la sanction et effacé d'Iris.`
            : null
        }
        confirmLabel="Retirer"
        pending={removeMutation.isPending}
        onConfirm={() => toRemove && removeMutation.mutate(toRemove)}
        onCancel={() => setToRemove(null)}
      />
    </section>
  );
}
