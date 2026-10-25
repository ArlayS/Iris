import { Fragment } from "react";

// Rend les segments calculés par l'API (jamais d'innerHTML, aucun calcul d'offset).
export default function Highlight({ segments, fallback = "", className = "" }) {
  const parts = Array.isArray(segments)
    ? segments.filter((segment) => segment && typeof segment.text === "string" && segment.text)
    : [];
  const classes = ["cz-highlight", className].filter(Boolean).join(" ");

  if (parts.length === 0) {
    return fallback ? <span className={classes}>{fallback}</span> : null;
  }

  return (
    <span className={classes}>
      {parts.map((segment, index) =>
        segment.match ? (
          <mark key={index} className="cz-mark">
            {segment.text}
          </mark>
        ) : (
          <Fragment key={index}>{segment.text}</Fragment>
        )
      )}
    </span>
  );
}
