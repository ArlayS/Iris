import { ArrowUpRight, RadioTower, ShieldCheck } from "lucide-react";


export default function LoginPage() {
  const backendUrl = process.env.REACT_APP_BACKEND_URL;
  return (
    <main className="login-page" data-testid="login-page">
      <section className="login-grid">
        <div className="login-identity">
          <div className="login-mark">I</div>
          <p className="eyebrow">IRIS / ESPACE D’ÉCOUTE</p>
          <h1>Un espace d’écoute, pour accompagner avec soin.</h1>
          <p className="login-description">
            Centralisez les demandes d’aide, les repères privés et la continuité de suivi des personnes accompagnées.
          </p>
          <div className="login-specs">
            <span><RadioTower size={15} /> ESPACE CONFIDENTIEL</span>
            <span><ShieldCheck size={15} /> ACCÈS HELPERS</span>
          </div>
        </div>
        <div className="login-action">
          <p className="eyebrow">ACCÈS SÉCURISÉ</p>
          <h2>Accéder à l’espace helpers</h2>
          <p>Connectez-vous avec Discord. L’accès est réservé aux membres ayant le rôle Helper du serveur.</p>
          <a
            className="discord-button"
            href={`${backendUrl}/api/auth/discord/login`}
            data-testid="discord-login-button"
          >
            Continuer avec Discord <ArrowUpRight size={18} />
          </a>
          <small>Une autorisation Discord et le rôle Helper sont requis.</small>
        </div>
      </section>
      <footer data-testid="login-footer">IRIS · ESPACE CONFIDENTIEL · ÉQUIPE HELPERS</footer>
    </main>
  );
}