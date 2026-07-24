import { ArrowUpRight, RadioTower, ShieldCheck } from "lucide-react";


export default function LoginPage() {
  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  return (
    <main className="login-page" data-testid="login-page">
      <section className="login-grid">
        <div className="login-identity">
          <div className="login-mark">I</div>
          <p className="eyebrow">IRIS / 01</p>
          <h1>Le poste de suivi des helpers.</h1>
          <p className="login-description">
            Centralisez les tickets Discord, les notes de suivi et les comptes-rendus vocaux.
          </p>
          <div className="login-specs">
            <span><RadioTower size={15} /> DISCORD SYNC</span>
            <span><ShieldCheck size={15} /> ACCÈS HELPERS</span>
          </div>
        </div>
        <div className="login-action">
          <p className="eyebrow">IDENTIFICATION</p>
          <h2>Accéder à Iris</h2>
          <p>Utilisez votre compte Discord pour ouvrir votre session helper.</p>
          <a
            className="discord-button"
            href={`${backendUrl}/api/auth/discord/login`}
            data-testid="discord-login-button"
          >
            Continuer avec Discord <ArrowUpRight size={18} />
          </a>
          <small>Accès réservé aux membres autorisés du serveur.</small>
        </div>
      </section>
      <footer data-testid="login-footer">IRIS · HELPER OPERATIONS · SYSTÈME INTERNE</footer>
    </main>
  );
}