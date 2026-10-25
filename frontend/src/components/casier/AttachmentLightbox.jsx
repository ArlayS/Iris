import "./casier-detail.css";

import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ChevronLeft, ChevronRight, Download, ImageOff, X } from "lucide-react";

import { attachmentHref, authorName, formatBytes, formatDate } from "./formatters";

// Visionneuse des images d'une sanction : `index` null = fermée ; flèches ← → entre les images.
export default function AttachmentLightbox({ attachments = [], index = null, onIndexChange, onClose }) {
  const count = attachments.length;
  const open = index !== null && index >= 0 && index < count;
  const attachment = open ? attachments[index] : null;
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [attachment?.id]);

  const go = (step) => {
    if (count < 2 || index === null) return;
    onIndexChange?.((index + step + count) % count);
  };

  const handleKeyDown = (event) => {
    if (event.defaultPrevented || count < 2) return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      go(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      go(1);
    }
  };

  const src = attachment ? attachmentHref(attachment.download_url) : null;
  const downloadHref = attachment ? attachmentHref(attachment.download_url, true) : null;
  const details = attachment
    ? [
        formatBytes(attachment.size),
        attachment.origin === "upload"
          ? `Ajouté par ${authorName(attachment.uploaded_by)}`
          : "Copié depuis le log Discord",
        formatDate(attachment.created_at),
      ].filter(Boolean)
    : [];

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose?.();
      }}
    >
      <Dialog.Portal>
        <div className="cz-dialog-root">
          <Dialog.Overlay className="cz-dialog-overlay" />
          <Dialog.Content className="cz-dialog cz-dialog--wide cz-lightbox" onKeyDown={handleKeyDown}>
            {attachment && (
              <>
                <div className="cz-dialog-header">
                  <div>
                    <p className="cz-dialog-eyebrow">
                      {count > 1 ? `Image ${index + 1} sur ${count}` : "Image jointe"}
                    </p>
                    <Dialog.Title className="cz-dialog-title">{attachment.filename || "Fichier"}</Dialog.Title>
                    <Dialog.Description className="cz-meta">{details.join(" · ")}</Dialog.Description>
                  </div>
                  <Dialog.Close className="cz-dialog-close" aria-label="Fermer">
                    <X size={18} aria-hidden="true" />
                  </Dialog.Close>
                </div>

                <div className="cz-lightbox-stage">
                  {src && !failed ? (
                    <img src={src} alt={attachment.filename || "Image jointe"} onError={() => setFailed(true)} />
                  ) : (
                    <div className="cz-lightbox-fallback">
                      <ImageOff size={28} aria-hidden="true" />
                      <p>Aperçu indisponible. Téléchargez le fichier pour l'ouvrir.</p>
                    </div>
                  )}

                  {count > 1 && (
                    <>
                      <button
                        type="button"
                        className="cz-icon-button cz-lightbox-nav cz-lightbox-nav--prev"
                        onClick={() => go(-1)}
                        aria-label="Image précédente"
                      >
                        <ChevronLeft size={20} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        className="cz-icon-button cz-lightbox-nav cz-lightbox-nav--next"
                        onClick={() => go(1)}
                        aria-label="Image suivante"
                      >
                        <ChevronRight size={20} aria-hidden="true" />
                      </button>
                    </>
                  )}
                </div>

                <div className="cz-dialog-footer">
                  {count > 1 && <p className="cz-dialog-footer-note">Flèches ← → pour passer d'une image à l'autre.</p>}
                  <Dialog.Close className="cz-button">Fermer</Dialog.Close>
                  {downloadHref && (
                    <a className="cz-button cz-button--primary" href={downloadHref} download={attachment.filename || true}>
                      <Download size={16} aria-hidden="true" />
                      Télécharger
                    </a>
                  )}
                </div>
              </>
            )}
          </Dialog.Content>
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
