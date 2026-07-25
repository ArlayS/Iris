import { Download, FileArchive, FileImage, FileText, FileUp, LoaderCircle, Trash2, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";


const formatSize = (size) => `${(size / 1024 / 1024).toFixed(size > 1024 * 1024 ? 1 : 2)} Mo`;
const formatDate = (date) => new Date(date).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });


function ResourceIcon({ type }) {
  if (type.includes("image")) return <FileImage size={25} />;
  if (type.includes("pdf")) return <FileArchive size={25} />;
  return <FileText size={25} />;
}


export default function ResourcesPage({ isAdmin }) {
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("Général");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const inputRef = useRef(null);

  const loadResources = () => {
    setLoading(true);
    api.get("/resources")
      .then((response) => setResources(response.data.resources))
      .catch((error) => toast.error(getErrorMessage(error)))
      .finally(() => setLoading(false));
  };

  useEffect(loadResources, []);

  const chooseFile = (selected) => {
    if (!selected) return;
    if (selected.size > 250 * 1024 * 1024) {
      toast.error("La taille maximale est de 250 Mo.");
      return;
    }
    setFile(selected);
    if (!title) setTitle(selected.name.replace(/\.[^.]+$/, ""));
  };

  const upload = async (event) => {
    event.preventDefault();
    if (!file || !title.trim()) return;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("title", title.trim());
    formData.append("description", description.trim());
    formData.append("category", category.trim() || "Général");
    setUploading(true);
    setProgress(0);
    try {
      const response = await api.post("/resources", formData, {
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) setProgress(Math.round((progressEvent.loaded * 100) / progressEvent.total));
        },
      });
      setResources((current) => [response.data, ...current]);
      setFile(null);
      setTitle("");
      setDescription("");
      setCategory("Général");
      if (inputRef.current) inputRef.current.value = "";
      toast.success("Ressource publiée.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setUploading(false);
      setProgress(0);
    }
  };

  const download = async (resource) => {
    try {
      const response = await api.get(`/resources/${resource.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = resource.original_filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const remove = async (resource) => {
    try {
      await api.delete(`/resources/${resource.id}`);
      setResources((current) => current.filter((item) => item.id !== resource.id));
      toast.success("Ressource retirée.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  return (
    <section className="page-content resources-page" data-testid="resources-page">
      <header className="page-header">
        <div><p className="eyebrow">BIBLIOTHÈQUE PARTAGÉE</p><h1>Ressources de l’équipe.</h1><p className="resources-intro">Règlements, repères et documents utiles à consulter à tout moment.</p></div>
      </header>

      {isAdmin && <form className="resource-upload-zone" onSubmit={upload} data-testid="resource-upload-form">
        <div className="resource-upload-copy"><span className="category-badge"><UploadCloud size={14} /> PUBLICATION ADMIN</span><h2>Ajouter une ressource</h2><p>PDF, Word, image ou texte · jusqu’à 250 Mo</p></div>
        <div className="resource-upload-fields">
          <input ref={inputRef} type="file" accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp,.gif,.txt" onChange={(event) => chooseFile(event.target.files?.[0])} data-testid="resource-file-input" />
          <div className="resource-text-fields"><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Titre de la ressource" required data-testid="resource-title-input" /><input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Catégorie" required data-testid="resource-category-input" /><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Courte description (facultatif)" data-testid="resource-description-input" /></div>
          {file && <p className="selected-resource" data-testid="selected-resource-file">{file.name} · {formatSize(file.size)}</p>}
          {uploading && <div className="upload-progress" data-testid="resource-upload-progress"><span style={{ width: `${progress}%` }} /><b>{progress}%</b></div>}
          <button className="calm-primary-button" disabled={uploading} type="submit" data-testid="upload-resource-button">{uploading ? <LoaderCircle className="spin" size={16} /> : <FileUp size={16} />}{uploading ? "Publication…" : "Publier la ressource"}</button>
        </div>
      </form>}

      {loading ? <div className="loading-page" data-testid="resources-loading"><LoaderCircle className="spin" size={25} /> Chargement des ressources…</div> : <div className="resource-grid" data-testid="resource-grid">{resources.length === 0 ? <p className="resources-empty" data-testid="resources-empty">Aucune ressource publiée pour le moment.</p> : resources.map((resource) => <article className="resource-card" key={resource.id} data-testid={`resource-card-${resource.id}`}><div className="resource-type"><ResourceIcon type={resource.content_type} /></div><span className="resource-category">{resource.category}</span><h2>{resource.title}</h2><p>{resource.description || resource.original_filename}</p><div className="resource-meta"><span>{formatSize(resource.size)}</span><span>{formatDate(resource.created_at)}</span></div><div className="resource-actions"><button type="button" onClick={() => download(resource)} data-testid={`download-resource-${resource.id}`}><Download size={15} /> Télécharger</button>{isAdmin && <button className="resource-delete-button" type="button" onClick={() => remove(resource)} data-testid={`delete-resource-${resource.id}`} aria-label="Retirer la ressource"><Trash2 size={15} /></button>}</div></article>)}</div>}
    </section>
  );
}