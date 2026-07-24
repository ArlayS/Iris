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
          <p className="eyebrow">IRIS / HELPER INTELLIGENCE</p>
          <h1>Chaque demande mérite un poste de commande.</h1>
          <p className="login-description">
            Une vision précise des conversations, décisions et passages en vocal de votre équipe Discord.
          </p>
          <div className="login-specs">
            <span><RadioTower size={15} /> DISCORD SYNC</span>
            <span><ShieldCheck size={15} /> ACCÈS HELPERS</span>
          </div>
        </div>
        <div className="login-action">
          <p className="eyebrow">POINT D’ENTRÉE</p>
          <h2>Accéder à Iris</h2>
          <p>Utilisez votre compte Discord pour ouvrir votre session helper.</p>
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
      <footer data-testid="login-footer">IRIS · HELPER OPERATIONS · SYSTÈME INTERNE</footer>
    </main>
  );
}