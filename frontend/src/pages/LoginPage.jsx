import { useEffect, useState } from "react";
import { AlertTriangle, ArrowUpRight, RadioTower, ShieldCheck } from "lucide-react";

// Le backend ne renvoie qu'un code : le texte affiché vient toujours d'ici.
const AUTH_ERROR_MESSAGES = {
  state_expired: "Session expirée, réessayez.",
  oauth_refused: "La connexion Discord a été refusée. Réessayez.",
  not_in_guild: "Votre compte Discord ne fait pas partie du serveur Iris.",
  missing_role: "Votre compte Discord ne possède pas un rôle autorisé pour Iris.",
  unavailable: "Connexion momentanément indisponible. Réessayez plus tard.",
};
const DEFAULT_AUTH_ERROR = "La connexion a échoué. Réessayez.";


export default function LoginPage() {
  const backendUrl = process.env.REACT_APP_BACKEND_URL;
  const [authError, setAuthError] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const error = params.get("auth_error");
    if (error) {
      setAuthError(
        Object.prototype.hasOwnProperty.call(AUTH_ERROR_MESSAGES, error)
          ? AUTH_ERROR_MESSAGES[error]
          : DEFAULT_AUTH_ERROR
      );
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  return (
    <main className="login-page" data-testid="login-page">
      <section className="login-grid">
        <div className="login-identity">
          <div className="login-mark"><img src="https://customer-assets-lqy194kg.emergentagent.net/job_iris-logs/artifacts/jhsbq3v9_image.png" alt="Iris" data-testid="login-iris-logo" /></div>
          <p className="eyebrow">IRIS / ESPACE DE GESTION</p>
          <h1>Un espace de gestion, pour accompagner avec soin.</h1>
          <p className="login-description">
            Centralisez les taches réalisées aux sein du Staff de L'Oasis.
          </p>
          <div className="login-specs">
            <span><RadioTower size={15} /> ESPACE CONFIDENTIEL</span>
            <span><ShieldCheck size={15} /> ACCÈS SÉCURISÉ</span>
          </div>
        </div>
        <div className="login-action">
          <h2>Accéder à votre espace</h2>
          <p>Connectez-vous avec Discord. L’accès est réservé aux membres ayant un rôle Staff sur le serveur.</p>


          
          {authError && (
            <div className="auth-error-card" data-testid="auth-error-message">
              <AlertTriangle size={18} />
              <p>{authError}</p>
            </div>
          )}
<a
            className="discord-button"
            href={`${backendUrl}/api/auth/discord/login`}
            data-testid="discord-login-button"
          >
            Continuer avec Discord <ArrowUpRight size={18} />
          </a>
          <small>Une connexion Discord et un rôle interne sont requis.</small>
        </div>
      </section>
      <footer data-testid="login-footer">IRIS · ESPACE CONFIDENTIEL · L'OASIS 2026</footer>
    </main>
  );
}
