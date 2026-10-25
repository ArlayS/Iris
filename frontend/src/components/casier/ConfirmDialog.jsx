import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { Loader2 } from "lucide-react";

const TONES = ["danger", "primary", "fiche"];

// Le parent garde la main sur `open` : il ferme après succès et laisse ouvert en cas d'erreur.
export default function ConfirmDialog({
  open,
  title,
  description = null,
  eyebrow = null,
  confirmLabel = "Confirmer",
  cancelLabel = "Annuler",
  tone = "danger",
  pending = false,
  onConfirm,
  onCancel,
  children = null,
}) {
  const buttonTone = TONES.includes(tone) ? tone : "danger";

  const handleOpenChange = (next) => {
    if (!next && !pending) onCancel?.();
  };

  const contentProps = description ? {} : { "aria-describedby": undefined };

  return (
    <AlertDialog.Root open={Boolean(open)} onOpenChange={handleOpenChange}>
      <AlertDialog.Portal>
        <div className="cz-dialog-root">
          <AlertDialog.Overlay className="cz-dialog-overlay cz-dialog-overlay--confirm" />
          <AlertDialog.Content
            className="cz-dialog cz-dialog--confirm"
            onEscapeKeyDown={(event) => {
              if (pending) event.preventDefault();
            }}
            {...contentProps}
          >
            <div className="cz-dialog-header">
              <div>
                {eyebrow && <p className="cz-dialog-eyebrow">{eyebrow}</p>}
                <AlertDialog.Title className="cz-dialog-title">{title}</AlertDialog.Title>
              </div>
            </div>

            {(description || children) && (
              <div className="cz-dialog-body">
                {description && (
                  <AlertDialog.Description asChild>
                    <div className="cz-dialog-description">{description}</div>
                  </AlertDialog.Description>
                )}
                {children}
              </div>
            )}

            <div className="cz-dialog-footer">
              <AlertDialog.Cancel className="cz-button" disabled={pending}>
                {cancelLabel}
              </AlertDialog.Cancel>
              <button
                type="button"
                className={`cz-button cz-button--${buttonTone}`}
                onClick={() => onConfirm?.()}
                disabled={pending}
                aria-busy={pending || undefined}
              >
                {pending && <Loader2 size={16} className="cz-spin" aria-hidden="true" />}
                {confirmLabel}
              </button>
            </div>
          </AlertDialog.Content>
        </div>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
