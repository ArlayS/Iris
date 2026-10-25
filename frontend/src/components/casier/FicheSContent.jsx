import SummaryReader from "../SummaryReader";

import "./casier-fiches-ia.css";
import FicheSErrorBoundary from "./FicheSErrorBoundary";
import { ficheReadableText, ficheReaderKey, isEditorEmpty, readerContentFor } from "./ficheContent";

const EMPTY_LABEL = "Cette fiche S ne contient pas de texte lisible.";

// Lecteur tolérant : BlockNote via SummaryReader, ancien texte ou HTML rendu en texte brut (jamais injecté).
export function FicheSReader({ fiche }) {
  const content = readerContentFor(fiche);

  // `key` : SummaryReader ne lit son contenu qu'à la création, on le remonte après chaque modification.
  if (content && !isEditorEmpty(content)) {
    return (
      <div className="cz-fiche-reader">
        <SummaryReader key={ficheReaderKey(fiche)} content={content} emptyLabel={EMPTY_LABEL} />
      </div>
    );
  }

  const text = ficheReadableText(fiche);
  if (!text.trim()) return <p className="cz-fiche-empty">{EMPTY_LABEL}</p>;
  return <p className="cz-fiche-text">{text}</p>;
}

export default function FicheSContent({ fiche }) {
  return (
    <FicheSErrorBoundary fiche={fiche}>
      <FicheSReader fiche={fiche} />
    </FicheSErrorBoundary>
  );
}
