import { ArrowUpRight, LoaderCircle, Play, RadioTower, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";

import { api, getErrorMessage } from "../api/client";


export default function LoginPage() {
  const backendUrl = process.env.REACT_APP_BACKEND_URL;
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [demoError, setDemoError] = useState("");

  const openDemo = async () => {
    setLoadingDemo(true);
    setDemoError("");
    try {
      await api.post("/auth/demo-session");
      window.location.assign("/");
    } catch (error) {
      setDemoError(getErrorMessage(error));
      setLoadingDemo(false);
    }
  };

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
          <div className="demo-divider"><span>OU EXPLORER</span></div>
          <button className="demo-access-button" type="button" onClick={openDemo} disabled={loadingDemo} data-testid="demo-access-btn">
            {loadingDemo ? <LoaderCircle className="spin" size={18} /> : <Play size={18} fill="currentColor" />}
            {loadingDemo ? "Ouverture du poste…" : "Accéder au mode démo"}
            <Sparkles size={16} />
          </button>
          {demoError && <p className="form-error" role="alert" data-testid="demo-access-error">{demoError}</p>}
          <small>3 dossiers fictifs, sans connexion à Discord réel.</small>
        </div>
      </section>
      <footer data-testid="login-footer">IRIS · ESPACE CONFIDENTIEL · ÉQUIPE HELPERS</footer>
    </main>
  );
}