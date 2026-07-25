import { LoaderCircle, Save, ShieldCheck, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";


export default function HelperProfilePage({ helper }) {
  const [triggers, setTriggers] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/profile/me")
      .then((response) => setTriggers(response.data.triggers || ""))
      .catch((error) => toast.error(getErrorMessage(error)))
      .finally(() => setLoading(false));
  }, []);

  const saveProfile = async () => {
    setSaving(true);
    try {
      await api.put("/profile/me", { triggers });
      toast.success("Profil helper enregistré.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="loading-page" data-testid="helper-profile-loading"><LoaderCircle className="spin" size={24} /> Chargement du profil…</div>;

  return (
    <section className="page-content helper-profile-page" data-testid="helper-profile-page">
      <header className="profile-hero">
        <span className="profile-avatar">{helper.avatar_url ? <img src={helper.avatar_url} alt="" /> : <UserRound size={24} />}</span>
        <div><p className="eyebrow">PROFIL HELPER</p><h1>{helper.global_name || helper.username}</h1><p>ID Discord · {helper.id}</p></div>
      </header>
      <section className="triggers-card" data-testid="helper-triggers-card">
        <div><span className="category-badge"><ShieldCheck size={14} /> ESPACE PERSONNEL</span><h2>Mes triggers</h2><p>Indiquez ce qui peut être difficile pour vous. Ces informations ne sont visibles que par vous et les administrateurs.</p></div>
        <textarea value={triggers} onChange={(event) => setTriggers(event.target.value)} placeholder="Écrivez ici les situations, sujets ou formulations à éviter…" maxLength={8000} data-testid="helper-triggers-input" />
        <button className="calm-primary-button" type="button" onClick={saveProfile} disabled={saving} data-testid="save-helper-profile-button">{saving ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />} Enregistrer mon profil</button>
      </section>
    </section>
  );
}