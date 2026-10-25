import { FICHE_DRAFT_PREFIX } from "./casierConstants";

// Lecture tolérante des fiches S : BlockNote (JSON), ancien texte brut ou ancien HTML.
// Le HTML n'est jamais injecté dans la page : DOMParser produit un document inerte dont on ne lit que le texte.

const TAG_PATTERN = /<[a-zA-Z][^>]*>/;
const MEDIA_BLOCK_TYPES = new Set(["image", "file", "video", "audio"]);
const MAX_DEPTH = 64;

/* ---------------------------------- */
/* Format                             */
/* ---------------------------------- */

function isBlockList(value) {
  return (
    Array.isArray(value) &&
    value.every((block) => block && typeof block === "object" && !Array.isArray(block) && typeof block.type === "string")
  );
}

// Liste de blocs si `content` est un JSON BlockNote valide (même règle que le serveur, `[]` compris), sinon null.
export function parseBlocks(content) {
  if (Array.isArray(content)) return isBlockList(content) ? content : null;
  if (typeof content !== "string") return null;
  const text = content.trim();
  if (!text.startsWith("[")) return null;
  try {
    const parsed = JSON.parse(text);
    return isBlockList(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

// "blocknote" | "html" | "text" (repli quand l'API ne fournit pas content_format).
export function detectFormat(content) {
  if (parseBlocks(content)) return "blocknote";
  if (typeof content === "string" && TAG_PATTERN.test(content)) return "html";
  return "text";
}

export function ficheFormat(fiche) {
  const format = fiche?.content_format;
  if (format === "blocknote" || format === "html" || format === "text") return format;
  return detectFormat(fiche?.content);
}

// Contenu à passer à SummaryReader, ou null s'il n'y a rien de lisible par BlockNote (format non blocknote,
// JSON invalide ou liste vide, que BlockNote refuse) : afficher alors ficheReadableText(fiche).
export function readerContentFor(fiche) {
  if (ficheFormat(fiche) !== "blocknote") return null;
  const blocks = parseBlocks(fiche?.content);
  return blocks && blocks.length ? fiche.content : null;
}

// Clé React du lecteur : remonte SummaryReader après chaque modification.
export function ficheReaderKey(fiche) {
  return `${fiche?.id ?? "fiche"}:${fiche?.updated_at ?? fiche?.created_at ?? ""}`;
}

/* ---------------------------------- */
/* Texte                              */
/* ---------------------------------- */

const normalizeNewlines = (text) => String(text ?? "").replace(/\r\n?/g, "\n");

function inlineText(content, depth = 0) {
  if (depth > MAX_DEPTH) return "";
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) {
    if (content && typeof content === "object" && content.type === "tableContent") return tableText(content, depth + 1);
    return "";
  }
  return content
    .map((item) => {
      if (typeof item === "string") return item;
      if (!item || typeof item !== "object") return "";
      if (item.type === "text") return typeof item.text === "string" ? item.text : "";
      if (item.type === "link") return inlineText(item.content, depth + 1);
      return typeof item.text === "string" ? item.text : "";
    })
    .join("");
}

function tableText(table, depth) {
  const rows = Array.isArray(table?.rows) ? table.rows : [];
  return rows
    .map((row) =>
      (Array.isArray(row?.cells) ? row.cells : [])
        .map((cell) => {
          if (Array.isArray(cell)) return inlineText(cell, depth + 1);
          if (cell && typeof cell === "object") return inlineText(cell.content, depth + 1);
          return "";
        })
        .map((text) => text.trim())
        .filter(Boolean)
        .join(" | ")
    )
    .filter(Boolean)
    .join("\n");
}

function collectBlockLines(blocks, lines, depth) {
  if (!Array.isArray(blocks) || depth > MAX_DEPTH) return;
  blocks.forEach((block) => {
    if (!block || typeof block !== "object") return;
    const parts = [];
    const text = inlineText(block.content, depth);
    if (text) parts.push(text);
    if (MEDIA_BLOCK_TYPES.has(block.type)) {
      const caption = block.props?.caption;
      const name = block.props?.name;
      if (typeof caption === "string" && caption.trim()) parts.push(caption);
      if (typeof name === "string" && name.trim()) parts.push(name);
    }
    if (parts.length) lines.push(parts.join(" "));
    collectBlockLines(block.children, lines, depth + 1);
  });
}

// Texte brut d'un document BlockNote (une ligne par bloc), même parcours que le serveur.
export function blocksToText(blocksOrJson) {
  const blocks = parseBlocks(blocksOrJson);
  if (!blocks) return "";
  const lines = [];
  collectBlockLines(blocks, lines, 0);
  return lines.join("\n");
}

const BLOCK_TAGS = new Set([
  "ADDRESS", "ARTICLE", "ASIDE", "BLOCKQUOTE", "DD", "DIV", "DL", "DT", "FIELDSET", "FIGCAPTION", "FIGURE",
  "FOOTER", "FORM", "H1", "H2", "H3", "H4", "H5", "H6", "HEADER", "HR", "LI", "MAIN", "NAV", "OL", "P", "PRE",
  "SECTION", "TABLE", "TBODY", "TFOOT", "THEAD", "TR", "UL",
]);
const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "TEMPLATE", "NOSCRIPT", "HEAD", "TITLE", "IFRAME", "OBJECT", "SVG", "MATH"]);

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };

function decodeEntities(text) {
  return text.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (whole, code) => {
    const lower = code.toLowerCase();
    if (lower.startsWith("#x")) {
      const value = parseInt(lower.slice(2), 16);
      return Number.isFinite(value) && value <= 0x10ffff ? String.fromCodePoint(value) : whole;
    }
    if (lower.startsWith("#")) {
      const value = parseInt(lower.slice(1), 10);
      return Number.isFinite(value) && value <= 0x10ffff ? String.fromCodePoint(value) : whole;
    }
    return ENTITIES[lower] ?? whole;
  });
}

function htmlToTextFallback(html) {
  const text = html
    .replace(/<(script|style|template|noscript)[^>]*>[\s\S]*?<\/\1\s*>/gi, "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li|h[1-6]|tr|blockquote|pre|ul|ol|table|section|article)\s*>/gi, "\n")
    .replace(/<[^>]*>/g, "");
  return decodeEntities(text)
    .split("\n")
    .map((line) => line.replace(/[ \t\f\v ]+/g, " ").trim())
    .join("\n");
}

function tidyLines(lines) {
  const out = [];
  lines.forEach((line) => {
    if (line === "" && (out.length === 0 || out[out.length - 1] === "")) return;
    out.push(line);
  });
  while (out.length && out[out.length - 1] === "") out.pop();
  return out.join("\n");
}

// Texte lisible d'un ancien HTML (un paragraphe par bloc p, li, h1–h6, div…), sans rien charger ni exécuter.
export function htmlToText(html) {
  if (typeof html !== "string" || !html.trim()) return "";
  if (typeof DOMParser === "undefined") return tidyLines(htmlToTextFallback(html).split("\n"));

  let doc;
  try {
    doc = new DOMParser().parseFromString(html, "text/html");
  } catch {
    return tidyLines(htmlToTextFallback(html).split("\n"));
  }

  const lines = [];
  const lists = [];
  let current = "";
  let prefix = "";
  let preDepth = 0;

  const flush = () => {
    const line = preDepth > 0 ? current.replace(/\s+$/, "") : current.replace(/\s+/g, " ").trim();
    if (line) {
      lines.push(`${prefix}${line}`);
      prefix = "";
    }
    current = "";
  };

  const walk = (node, depth) => {
    if (depth > MAX_DEPTH) return;
    node.childNodes.forEach((child) => {
      if (child.nodeType === 3) {
        const value = child.nodeValue || "";
        if (preDepth > 0) {
          const parts = value.split("\n");
          parts.forEach((part, index) => {
            if (index > 0) flush();
            current += part;
          });
        } else {
          current += value;
        }
        return;
      }
      if (child.nodeType !== 1) return;
      const tag = String(child.tagName || "").toUpperCase();
      if (SKIP_TAGS.has(tag)) return;
      if (tag === "BR") {
        flush();
        return;
      }
      if (tag === "TD" || tag === "TH") {
        if (current.trim()) current += " | ";
        walk(child, depth + 1);
        return;
      }
      if (!BLOCK_TAGS.has(tag)) {
        walk(child, depth + 1);
        return;
      }

      flush();
      const before = lines.length;
      if (tag === "UL" || tag === "OL") lists.push({ ordered: tag === "OL", index: 0 });
      if (tag === "LI") {
        const list = lists[lists.length - 1];
        const indent = "  ".repeat(Math.max(0, lists.length - 1));
        if (list) list.index += 1;
        prefix = `${indent}${list?.ordered ? `${list.index}. ` : "• "}`;
      }
      if (tag === "PRE") preDepth += 1;
      walk(child, depth + 1);
      flush();
      if (tag === "PRE") preDepth -= 1;
      if (tag === "UL" || tag === "OL") lists.pop();
      if (tag === "LI") prefix = "";
      // Paragraphe vide (ligne blanche de l'ancien éditeur) : ligne vide conservée.
      if (tag === "P" && lines.length === before) lines.push("");
    });
  };

  walk(doc.body || doc.documentElement, 0);
  flush();
  return tidyLines(lines);
}

// Texte affichable d'une fiche, quel que soit son format (repli de la limite d'erreur compris).
export function ficheReadableText(fiche) {
  const format = ficheFormat(fiche);
  const content = typeof fiche?.content === "string" ? fiche.content : "";
  if (format === "html") return htmlToText(content);
  if (format === "text") return normalizeNewlines(content);
  if (typeof fiche?.content_text === "string" && fiche.content_text.trim()) return fiche.content_text;
  return blocksToText(content);
}

/* ---------------------------------- */
/* Conversion pour l'éditeur          */
/* ---------------------------------- */

// Un paragraphe par ligne, lignes vides gardées (contenu [] : ProseMirror refuse les nœuds texte vides).
export function textToBlocks(text) {
  return normalizeNewlines(text)
    .split("\n")
    .map((line) => ({
      type: "paragraph",
      content: line ? [{ type: "text", text: line, styles: {} }] : [],
    }));
}

// JSON BlockNote (chaîne) pour l'éditeur depuis un ancien contenu texte/HTML ; blocknote → inchangé ; vide → "".
export function legacyToBlocksJSON(content, format) {
  if (typeof content !== "string" || !content.trim()) return "";
  const kind = format || detectFormat(content);
  if (kind === "blocknote") {
    const blocks = parseBlocks(content);
    // BlockNote refuse un document initial vide (`[]`) : l'éditeur part alors de zéro.
    if (blocks) return blocks.length ? content : "";
    return JSON.stringify(textToBlocks(content));
  }
  const text = kind === "html" ? htmlToText(content) : content;
  if (!text.trim()) return "";
  return JSON.stringify(textToBlocks(text));
}

// Valeur initiale de l'éditeur pour une fiche existante (null → nouvelle fiche, "").
export function editorValueFor(fiche) {
  if (!fiche) return "";
  const content = typeof fiche.content === "string" ? fiche.content : "";
  const format = ficheFormat(fiche);
  if (format === "blocknote" && !parseBlocks(content)) {
    // JSON annoncé mais illisible : on repart du texte extrait par le serveur.
    return legacyToBlocksJSON(fiche.content_text || "", "text");
  }
  return legacyToBlocksJSON(content, format);
}

function hasMedia(blocks, depth) {
  if (!Array.isArray(blocks) || depth > MAX_DEPTH) return false;
  return blocks.some((block) => {
    if (!block || typeof block !== "object") return false;
    const url = block.props?.url;
    if (MEDIA_BLOCK_TYPES.has(block.type) && typeof url === "string" && url.trim()) return true;
    return hasMedia(block.children, depth + 1);
  });
}

// Même règle que le serveur (422 « La fiche S est vide. ») : aucun texte et aucun média avec une URL.
export function isEditorEmpty(value) {
  if (value === null || value === undefined) return true;
  const blocks = parseBlocks(value);
  if (!blocks) return typeof value === "string" ? !value.trim() : true;
  return !blocksToText(blocks).trim() && !hasMedia(blocks, 0);
}

/* ---------------------------------- */
/* Brouillon local                    */
/* ---------------------------------- */

export function ficheDraftKey(casierId, ficheId) {
  return `${FICHE_DRAFT_PREFIX}${casierId}.${ficheId || "new"}`;
}

function getStorage() {
  if (typeof window === "undefined") return null;
  return window.localStorage;
}

// { title, content, savedAt } ou null (absent, illisible ou stockage bloqué).
export function readFicheDraft(casierId, ficheId) {
  try {
    const raw = getStorage()?.getItem(ficheDraftKey(casierId, ficheId));
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") return null;
    const savedAt = Number(data.saved_at);
    return {
      title: typeof data.title === "string" ? data.title : "",
      content: typeof data.content === "string" ? data.content : "",
      savedAt: Number.isFinite(savedAt) ? savedAt : 0,
    };
  } catch {
    return null;
  }
}

export function writeFicheDraft(casierId, ficheId, { title = "", content = "" } = {}) {
  try {
    const storage = getStorage();
    if (!storage) return false;
    storage.setItem(ficheDraftKey(casierId, ficheId), JSON.stringify({ title, content, saved_at: Date.now() }));
    return true;
  } catch {
    return false;
  }
}

export function clearFicheDraft(casierId, ficheId) {
  try {
    getStorage()?.removeItem(ficheDraftKey(casierId, ficheId));
  } catch {
    // Stockage indisponible : rien à effacer.
  }
}

// Brouillon à proposer : plus récent que la dernière version enregistrée de la fiche.
export function isDraftNewer(draft, fiche) {
  if (!draft) return false;
  if (!fiche) return true;
  const reference = Date.parse(fiche.updated_at || fiche.created_at || "");
  if (!Number.isFinite(reference)) return true;
  return draft.savedAt > reference;
}
