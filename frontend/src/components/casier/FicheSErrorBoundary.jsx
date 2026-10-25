import { Component } from "react";

import "./casier-fiches-ia.css";
import { ficheReadableText, ficheReaderKey } from "./ficheContent";

function fallbackText(fiche) {
  try {
    const text = ficheReadableText(fiche);
    if (text && text.trim()) return text;
  } catch {
    // Lecture impossible : on tente le texte extrait par le serveur.
  }
  return typeof fiche?.content_text === "string" ? fiche.content_text : "";
}

// Un document BlockNote invalide ne doit jamais faire tomber la page : repli sur le texte brut.
// Réinitialisée quand la fiche change (id ou date de modification).
export default class FicheSErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null, resetKey: ficheReaderKey(props.fiche) };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  static getDerivedStateFromProps(props, state) {
    const resetKey = ficheReaderKey(props.fiche);
    if (resetKey !== state.resetKey) return { resetKey, error: null };
    return null;
  }

  componentDidCatch(error, info) {
    console.error("Fiche S : mise en forme illisible.", error, info?.componentStack);
  }

  render() {
    const { error } = this.state;
    const { fiche, children } = this.props;
    if (!error) return children ?? null;

    const text = fallbackText(fiche);
    return (
      <div className="cz-fiche-fallback">
        {text.trim() ? (
          <p className="cz-fiche-text">{text}</p>
        ) : (
          <p className="cz-fiche-empty">Cette fiche S ne contient pas de texte lisible.</p>
        )}
        <p className="cz-fiche-fallback-note">Mise en forme indisponible pour cette fiche.</p>
      </div>
    );
  }
}
