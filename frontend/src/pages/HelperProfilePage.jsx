import { useEffect, useState } from "react";
import {
  ArrowRight,
  LoaderCircle,
  Save,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";
import "@/Profile.css";

export default function HelperProfilePage({ helper }) {
  const [triggers, setTriggers] = useState("");
  const [savedTriggers, setSavedTriggers] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [avatarError, setAvatarError] = useState(false);

  const pseudo =
    helper?.global_name ||
    helper?.display_name ||
    helper?.username ||
    "Mon compte";

  const hasChanges = triggers !== savedTriggers;

  useEffect(() => {
    document.body.classList.add("profile-no-nav");

    return () => {
      document.body.classList.remove("profile-no-nav");
    };
  }, []);

  useEffect(() => {
    setAvatarError(false);
  }, [helper?.avatar_url]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    setLoading(true);
    setLoadError("");

    const loadProfile = async () => {
      try {
        const response = await api.get("/profile/me", {
          signal: controller.signal,
        });

        if (!active) return;

        const value = response.data.triggers || "";
        setTriggers(value);
        setSavedTriggers(value);
      } catch (error) {
        if (!active || controller.signal.aborted) return;

        setLoadError(getErrorMessage(error));
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadProfile();

    return () => {
      active = false;
      controller.abort();
    };
  }, [helper?.id, reloadKey]);

  const saveProfile = async (event) => {
    event.preventDefault();

    if (loading || saving || loadError || !hasChanges) return;

    const valueToSave = triggers;

    setSaving(true);

    try {
      await api.put("/profile/me", {
        triggers: valueToSave,
      });

      setSavedTriggers(valueToSave);
      toast.success("Profil enregistré.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      className="hp-page"
      data-testid="helper-profile-page"
    >
      <header className="hp-header">
        <div>
          <p className="hp-eyebrow">ESPACE PERSONNEL</p>
          <h1>Mon profil</h1>
          <p className="hp-intro">
            Un espace pour préciser vos limites et accompagner
            les membres à votre rythme.
          </p>
        </div>

        <Link to="/" className="hp-home-button">
          Accueil
          <ArrowRight size={18} aria-hidden="true" />
        </Link>
      </header>

      <div className="hp-layout">
        <aside className="hp-identity-card">
          <span className="hp-avatar">
            {helper?.avatar_url && !avatarError ? (
              <img
                src={helper.avatar_url}
                alt=""
                onError={() => setAvatarError(true)}
              />
            ) : (
              <UserRound size={34} aria-hidden="true" />
            )}
          </span>

          <p className="hp-eyebrow">MON COMPTE DISCORD</p>
          <h2>{pseudo}</h2>

          {helper?.username && (
            <p className="hp-username">@{helper.username}</p>
          )}

          <div className="hp-identity-detail">
            <span>Identifiant Discord</span>
            <code>{helper?.id || "Non disponible"}</code>
          </div>

          <p className="hp-identity-note">
            Votre nom et votre avatar proviennent de votre
            compte Discord.
          </p>
        </aside>

        <section
          className="hp-preferences-card"
          data-testid="helper-triggers-card"
          aria-labelledby="hp-triggers-title"
        >
          <header className="hp-card-header">
            <span className="hp-card-icon">
              <ShieldCheck size={23} aria-hidden="true" />
            </span>

            <div>
              <p className="hp-eyebrow">MES REPÈRES</p>
              <h2 id="hp-triggers-title">
                Mes limites et sujets sensibles
              </h2>
            </div>
          </header>

          {loading ? (
            <div
              className="hp-state"
              role="status"
              data-testid="helper-profile-loading"
            >
              <LoaderCircle
                className="hp-spin"
                size={23}
                aria-hidden="true"
              />
              Chargement du profil…
            </div>
          ) : loadError ? (
            <div className="hp-load-error" role="alert">
              <h3>Le profil n’a pas pu être chargé.</h3>
              <p>{loadError}</p>

              <button
                type="button"
                className="hp-secondary-button"
                onClick={() => setReloadKey((value) => value + 1)}
              >
                Réessayer
              </button>
            </div>
          ) : (
            <form onSubmit={saveProfile} className="hp-form">
              <p className="hp-description" id="hp-triggers-help">
                Indiquez les situations, sujets ou formulations
                qui peuvent être difficiles pour vous.
                Vous pouvez modifier ces informations à tout moment.
              </p>

              <label htmlFor="hp-triggers">
                Mes triggers et points de vigilance
              </label>

              <textarea
                id="hp-triggers"
                value={triggers}
                onChange={(event) =>
                  setTriggers(event.target.value)
                }
                placeholder={
                  "Exemples : certains sujets sensibles, " +
                  "des situations à éviter ou des précautions " +
                  "utiles lors de l’attribution d’un suivi…"
                }
                maxLength={8000}
                rows={9}
                disabled={saving}
                aria-describedby="hp-triggers-help hp-character-count"
                data-testid="helper-triggers-input"
              />

              <div className="hp-field-footer">
                <span className="hp-field-hint">
                  Renseignez uniquement ce que vous souhaitez partager.
                </span>

                <span id="hp-character-count">
                  {triggers.length.toLocaleString("fr-FR")} / 8 000
                </span>
              </div>

              <footer className="hp-save-footer">
                <span
                  className={`hp-save-state ${
                    hasChanges ? "has-changes" : ""
                  }`}
                  role="status"
                >
                  {saving
                    ? "Enregistrement en cours…"
                    : hasChanges
                      ? "Modifications non enregistrées"
                      : "Aucune modification en attente"}
                </span>

                <button
                  className="hp-save-button"
                  type="submit"
                  disabled={saving || !hasChanges}
                  data-testid="save-helper-profile-button"
                >
                  {saving ? (
                    <LoaderCircle
                      className="hp-spin"
                      size={17}
                      aria-hidden="true"
                    />
                  ) : (
                    <Save size={17} aria-hidden="true" />
                  )}

                  {saving ? "Enregistrement…" : "Enregistrer mon profil"}
                </button>
              </footer>
            </form>
          )}
        </section>
      </div>
    </section>
  );
}
