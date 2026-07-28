export function renderMarkdown(source) {
  const escapeHtml = (text) =>
    text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const lines = escapeHtml(source || "").split("\n");
  const html = [];
  let inList = false;
  let inCode = false;

  for (const rawLine of lines) {
    if (rawLine.trim().startsWith("```")) {
      inCode = !inCode;
      html.push(inCode ? "<pre><code>" : "</code></pre>");
      continue;
    }
    if (inCode) {
      html.push(rawLine + "\n");
      continue;
    }

    let line = rawLine
      .replace(/^### (.*)$/, "<h3>$1</h3>")
      .replace(/^## (.*)$/, "<h2>$1</h2>")
      .replace(/^# (.*)$/, "<h1>$1</h1>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`(.+?)`/g, "<code>$1</code>")
      .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');

    if (/^- /.test(rawLine)) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${line.replace(/^- /, "")}</li>`);
      continue;
    }
    if (inList) {
      html.push("</ul>");
      inList = false;
    }

    if (line.trim() === "") {
      html.push("<br />");
    } else if (/^<h[1-3]>/.test(line)) {
      html.push(line);
    } else {
      html.push(`<p>${line}</p>`);
    }
  }
  if (inList) html.push("</ul>");
  if (inCode) html.push("</code></pre>");
  return html.join("\n");
}
