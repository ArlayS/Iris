import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Download,
  Eye,
  FileText,
  FolderOpen,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import "@/ResourcesLibrary.css";

function normalize(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function formatSize(bytes) {
  const size = Number(bytes || 0);

  if (!size) return "—";

  if (size < 1024) return `${size} o`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} Ko`;

  return `${(size / (1024 * 1024)).toFixed(1)} Mo`;
}

function formatDate(value) {
  const date = new Date(value);

  if (!value || Number.isNaN(date.getTime())) {
    return "Non renseignée";
  }

  return date.toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function fileExtension(name) {
  return String(name || "")
    .split(".")
    .pop()
    .slice(0, 4)
    .toUpperCase();
}

function isImage(resource) {
  return String(resource.mime_type || "").startsWith("image/");
}

function isPdf(resource) {
  return (
    String(resource.mime_type || "").includes("pdf") ||
    String(resource.original_filename || "")
      .toLowerCase()
      .endsWith(".pdf")
  );
}

function ResourcePreview({ resource }) {
  if (isImage(resource) && resource.file_url) {
    return (
      <img
        src={resource.file_url}
        alt=""
        loading="lazy"
        className="rl-card-preview-image"
      />
    );
  }

  if (isPdf(resource)) {
    return (
      <span className="rl-card-preview rl-card-preview-pdf">
        <FileText size={28} aria-hidden="true" />
        PDF
      </span>
    );
  }

  return (
    <span className="rl-card-preview">
      <FileText size={28} aria-hidden="true" />
      {fileExtension(resource.original_filename) || "FICHIER"}
    </span>
  );
}

function PreviewModal({ resource, onClose }) {
  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  return (
    <div
      className="rl-modal"
      role="dialog"
      aria-modal="true"
      aria-label={`Aperçu de ${resource.title}`}
      onClick={onClose}
    >
      <div
        className="rl-modal-panel"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="rl-modal-header">
          <div>
            <p>{resource.category || "Ressource"}</p>
            <h2>{resource.title}</h2>
          </div>

          <button
            type="button"
            className="rl-modal-close"
            onClick={onClose}
            aria-label="Fermer l’aperçu"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <div className="rl-modal-body">
          {isImage(resource) && resource.file_url ? (
            <img
              src={resource.file_url}
              alt={resource.title}
              className="rl-modal-image"
            />
          ) : (
            <div className="rl-modal-placeholder">
              <FileText size={38} aria-hidden="true" />

              <p>
                L’aperçu intégré n’est pas disponible pour ce
                type de fichier.
              </p>

              <a
                href={resource.file_url}
                target="_blank"
                rel="noreferrer"
                className="rl-empty-button"
              >
                Ouvrir dans un nouvel onglet
              </a>
            </div>
          )}
        </div>

        <footer className="rl-modal-footer">
          <span>
            {resource.description ||
              resource.original_filename ||
              "Ressource partagée"}
          </span>

          <a
            href={resource.file_url}
            target="_blank"
            rel="noreferrer"
            className="rl-primary-button"
          >
            <Download size={16} aria-hidden="true" />
            Télécharger
          </a>
        </footer>
      </div>
    </div>
  );
}

export default function ResourcesPage({
  resources = [],
  loading = false,
  error = "",
  isAdmin = false,
  onPreview,
  onDownload,
  onRemove,
  onRetry,
}) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [previewed, setPreviewed] = useState(null);

  useEffect(() => {
    document.body.classList.add("resources-library-no-nav");

    return () => {
      document.body.classList.remove("resources-library-no-nav");
    };
  }, []);

  const categories = useMemo(() => {
    const values = [
      ...new Set(
        resources
          .map((resource) => resource.category)
          .filter(Boolean)
      ),
    ];

    return values.sort((a, b) => a.localeCompare(b, "fr"));
  }, [resources]);

  const visibleResources = useMemo(() => {
    const term = normalize(search.trim());

    return resources.filter((resource) => {
      if (category !== "all" && resource.category !== category) {
        return false;
      }

      if (!term) return true;

      const text = normalize(
        [
          resource.title,
          resource.description,
          resource.category,
          resource.original_filename,
        ].join(" ")
      );

      return text.includes(term);
    });
  }, [resources, search, category]);

  const hasFilters = Boolean(search.trim() || category !== "all");

  const clearFilters = () => {
    setSearch("");
    setCategory("all");
  };

  const openPreview = (resource) => {
    if (onPreview) {
      onPreview(resource);
    } else {
      setPreviewed(resource);
    }
  };

  return (
    <section
      className="rl-page"
      data-testid="resources-page"
    >
      <header className="rl-header">
        <div>
          <p className="rl-eyebrow">ESPACE HELPER</p>

          <h1>Ressources</h1>

          <p className="rl-intro">
            Une bibliothèque partagée pour retrouver les
            documents, repères et supports utiles aux suivis.
          </p>
        </div>

        <div className="rl-header-actions">
          <Link to="/" className="rl-ghost-button">
            Accueil
            <ArrowRight size={17} aria-hidden="true" />
          </Link>

          {isAdmin && (
            <Link to="/resources/new" className="rl-primary-button">
              <Upload size={16} aria-hidden="true" />
              Ajouter une ressource
            </Link>
          )}
        </div>
      </header>

      <section className="rl-toolbar" aria-label="Filtres de ressources">
        <label className="rl-search">
          <Search size={17} aria-hidden="true" />

          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Rechercher un document, un thème ou un fichier…"
            aria-label="Rechercher une ressource"
          />
        </label>

        <div className="rl-filters">
          <button
            type="button"
            className={category === "all" ? "is-selected" : ""}
            aria-pressed={category === "all"}
            onClick={() => setCategory("all")}
          >
            Toutes les catégories
          </button>

          {categories.map((value) => (
            <button
              key={value}
              type="button"
              className={category === value ? "is-selected" : ""}
              aria-pressed={category === value}
              onClick={() => setCategory(value)}
            >
              {value}
            </button>
          ))}

          {hasFilters && (
            <button
              type="button"
              className="rl-reset"
              onClick={clearFilters}
            >
              <X size={13} aria-hidden="true" />
              Effacer
            </button>
          )}
        </div>
      </section>

      {loading ? (
        <div className="rl-state" role="status">
          <p>Chargement des ressources…</p>
        </div>
      ) : error ? (
        <div className="rl-state rl-error" role="alert">
          <h2>Les ressources n’ont pas pu être chargées.</h2>
          <p>{error}</p>

          {onRetry && (
            <button
              type="button"
              className="rl-empty-button"
              onClick={onRetry}
            >
              Réessayer
            </button>
          )}
        </div>
      ) : visibleResources.length === 0 ? (
        <div
          className="rl-state"
          data-testid="resources-empty-state"
        >
          <FolderOpen size={32} aria-hidden="true" />

          <h2>
            {hasFilters
              ? "Aucune ressource ne correspond à cette sélection."
              : "La bibliothèque est vide pour le moment."}
          </h2>

          <p>
            {hasFilters
              ? "Essayez une autre recherche ou retirez les filtres."
              : "Les documents ajoutés par les responsables apparaîtront ici."}
          </p>

          {hasFilters ? (
            <button
              type="button"
              className="rl-empty-button"
              onClick={clearFilters}
            >
              Afficher toutes les ressources
            </button>
          ) : isAdmin ? (
            <Link to="/resources/new" className="rl-empty-button">
              <Upload size={15} aria-hidden="true" />
              Ajouter une ressource
            </Link>
          ) : null}
        </div>
      ) : (
        <>
          <p className="rl-result" role="status">
            {visibleResources.length} ressource
            {visibleResources.length > 1 ? "s" : ""} disponible
            {visibleResources.length > 1 ? "s" : ""}
          </p>

          <div className="rl-grid">
            {visibleResources.map((resource) => (
              <article
                key={resource.id}
                className="rl-card"
                data-testid={`resource-card-${resource.id}`}
              >
                <ResourcePreview resource={resource} />

                <div className="rl-card-body">
                  {resource.category && (
                    <span className="rl-card-category">
                      {resource.category}
                    </span>
                  )}

                  <h2>{resource.title}</h2>

                  <p>
                    {resource.description ||
                      resource.original_filename ||
                      "Ressource partagée"}
                  </p>

                  <span className="rl-card-meta">
                    {formatSize(resource.size)} ·{" "}
                    {formatDate(resource.created_at)}
                  </span>
                </div>

                <div className="rl-card-actions">
                  <button
                    type="button"
                    onClick={() => openPreview(resource)}
                    data-testid={`preview-resource-${resource.id}`}
                  >
                    <Eye size={15} aria-hidden="true" />
                    Aperçu
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      onDownload
                        ? onDownload(resource)
                        : window.open(
                            resource.file_url,
                            "_blank",
                            "noopener"
                          )
                    }
                    data-testid={`download-resource-${resource.id}`}
                  >
                    <Download size={15} aria-hidden="true" />
                    Télécharger
                  </button>

                  {isAdmin && (
                    <button
                      type="button"
                      className="rl-danger"
                      onClick={() => onRemove?.(resource)}
                      data-testid={`delete-resource-${resource.id}`}
                      aria-label={`Retirer ${resource.title}`}
                    >
                      <Trash2 size={15} aria-hidden="true" />
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </>
      )}

      <footer className="rl-footer">
        <span>
          <BookOpen size={15} aria-hidden="true" />
          Les ressources restent accessibles aux helpers.
        </span>

        <Link to="/archives">
          Consulter les archives
          <ArrowRight size={15} aria-hidden="true" />
        </Link>
      </footer>

      {previewed && (
        <PreviewModal
          resource={previewed}
          onClose={() => setPreviewed(null)}
        />
      )}
    </section>
  );
}
