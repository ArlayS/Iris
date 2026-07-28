import { useMemo } from "react";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";
import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";

export default function SummaryReader({ content }) {
  const initialBlocks = useMemo(() => {
    if (!content || typeof content !== "string" || content.trim().length === 0) {
      return undefined;
    }
    try {
      return JSON.parse(content);
    } catch (err) {
      console.error("Erreur lors du chargement du contenu:", err);
      return undefined;
    }
  }, [content]);

  const editor = useCreateBlockNote({
    initialContent: initialBlocks,
  });

  if (!content || content.trim().length === 0) {
    return <p className="dashboard-empty">Aucun résumé rédigé pour le moment.</p>;
  }

  return (
    <div className="tiptap-editor tiptap-readonly">
      <BlockNoteView editor={editor} editable={false} theme="light" />
    </div>
  );
}
