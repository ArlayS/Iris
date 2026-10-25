// Libellés par défaut ; les clés sont les suffixes `.cz-pill--<variante>` (les `tone` de casierConstants).
export const PILL_LABELS = {
  banni: "Banni",
  kick: "Kick",
  mute: "Mute",
  averti: "Averti",
  vierge: "Vierge",
  rappel: "Rappel à l'ordre",
  fiche: "Fiche S",
  prevention: "Prévention",
  ia: "IA",
  "ia-0": "Sans gravité",
  "ia-1": "Gravité 1",
  "ia-2": "Gravité 2",
  "ia-3": "Gravité 3",
  "review-a_traiter": "À traiter",
  "review-pertinent": "Pertinent",
  "review-faux_positif": "Faux positif",
  neutral: "",
};

const ICON_SIZES = { sm: 12, md: 13, lg: 15 };

function readableValue(raw) {
  const text = raw.replace(/_/g, " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "Inconnu";
}

export default function StatusPill({
  status,
  variant,
  size = "md",
  icon: Icon = null,
  title,
  className = "",
  children,
}) {
  const raw = String(variant ?? status ?? "");
  const known = Object.prototype.hasOwnProperty.call(PILL_LABELS, raw);
  const resolved = known ? raw : "neutral";
  const label = children ?? (known ? PILL_LABELS[raw] : readableValue(raw));
  const sizeClass = size === "sm" || size === "lg" ? `cz-pill--${size}` : "";
  const classes = ["cz-pill", `cz-pill--${resolved}`, sizeClass, className].filter(Boolean).join(" ");

  return (
    <span className={classes} title={title}>
      {Icon && <Icon size={ICON_SIZES[size] || ICON_SIZES.md} aria-hidden="true" />}
      <span className="cz-pill-label">{label}</span>
    </span>
  );
}
