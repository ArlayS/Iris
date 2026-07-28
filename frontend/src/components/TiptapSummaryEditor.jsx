import { useEffect, useRef } from "react";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";
import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";
import { api } from "../api/client";

async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await api.post("/staff/meetings/upload-image", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  return response.data.url;
}

export default function TiptapSummaryEditor({
  value,
  onChange,
  placeholder = "Rédiger le résumé…",
}) {
  const editor = useCreateBlockNote({
    uploadFile,
  });

  const hasLoadedInitialContent = useRef(false);

  useEffect(() => {
    if (!editor || hasLoadedInitialContent.current) {
      return;
    }
    hasLoadedInitialContent.current = true;

    const loadContent = async () => {
      if (value && typeof value === "string" && value.trim().length > 0) {
        try {
          const blocks = await editor.tryParseMarkdownToBlocks(value);
          editor.replaceBlocks(editor.document, blocks);
        } catch (err) {
          console.error("Erreur lors du chargement du markdown:", err);
        }
      }
    };

    loadContent();
  }, [editor, value]);

  const handleChange = async () => {
    try {
      const markdown = await editor.blocksToMarkdownLossy(editor.document);
      onChange(markdown);
    } catch (err) {
      console.error("Erreur lors de la conversion en markdown:", err);
    }
  };

  return (
    <div className="tiptap-editor">
      <BlockNoteView
        editor={editor}
        onChange={handleChange}
        theme="light"
        placeholder={placeholder}
      />
    </div>
  );
}
