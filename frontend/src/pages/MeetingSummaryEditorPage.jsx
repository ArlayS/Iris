import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";
import { renderMarkdown } from "../utils/markdown";


export default function MeetingSummaryEditorPage() {
  const { meetingId } = useParams();
  const navigate = useNavigate();
  const isNew = meetingId === "new";

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isNew) return;
    api.get(`/staff/meetings/${meetingId}`)
      .then((response) => {
        setTitle(response.data.title);
        setContent(response.data.content_markdown);
      })
      .catch((error) => toast.error(getErrorMessage(error)))
      .finally(() => setLoading(false));
  }, [meetingId, isNew]);

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      if (isNew) {
        const response = await api.post("/staff/meetings", { title, content_markdown: content });
        toast.success("Résumé créé.");
        navigate(`/staff/meetings/${response.data.id}`, { replace: true });
      } else {
        await api.put(`/staff/meetings/${meetingId}`, { title, content_markdown: content });
        toast.success("Résumé mis à jour.");
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p className="page-content">Chargement…</p>;

  return (
    <section className="page-content staff-page" data-testid="meeting-summary-editor-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>{isNew ? "Nouveau résumé" : "Modifier le résumé"}</h1>
        </div>
      </header>

      <form className="meeting-editor" onSubmit={save}>
        <input
          className="meeting-title-input"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Titre de la réunion"
          maxLength={160}
          required
        />
        <div className="meeting-editor-grid">
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder={"# Points abordés\n- ...\n**Décisions :**"}
            rows={20}
          />
          <div className="meeting-preview" dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
        </div>
        <button className="calm-primary-button" type="submit" disabled={saving}>
          {saving ? "Enregistrement…" : "Enregistrer"}
        </button>
      </form>
    </section>
  );
}
