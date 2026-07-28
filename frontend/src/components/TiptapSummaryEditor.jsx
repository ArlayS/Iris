import { useEffect } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { Markdown } from "tiptap-markdown";
import {
  Bold,
  Heading2,
  Italic,
  List,
  ListOrdered,
  Quote,
  Redo2,
  Undo2,
} from "lucide-react";

export default function TiptapSummaryEditor({
  value,
  onChange,
  placeholder = "Rédiger le résumé…",
  autoFocus = false,
}) {
  const safeValue = typeof value === "string" ? value : "";

  const editor = useEditor({
    extensions: [
      StarterKit,
      Placeholder.configure({ placeholder }),
      Markdown.configure({ html: false, transformPastedText: true }),
    ],
    content: safeValue,
    autofocus: autoFocus ? "end" : false,
    immediatelyRender: false,
    onUpdate: ({ editor: current }) => {
      try {
        onChange(current.storage.markdown.getMarkdown());
      } catch (err) {
        console.error("Erreur lors de la récupération du markdown:", err);
      }
    },
  });

  useEffect(() => {
    if (!editor) {
      return;
    }
    try {
      const currentMarkdown = editor.storage.markdown.getMarkdown();
      if (safeValue !== currentMarkdown) {
        editor.commands.setContent(safeValue, false);
      }
    } catch (err) {
      console.error("Erreur setContent Tiptap:", err, "value reçue:", value);
    }
  }, [editor, safeValue]);

  if (!editor) {
    return null;
  }

  return (
    <div className="tiptap-editor">
      <div className="tiptap-toolbar">
        <button
          type="button"
          className={editor.isActive("bold") ? "is-active" : ""}
          onClick={() => editor.chain().focus().toggleBold().run()}
          aria-label="Gras"
        >
          <Bold size={15} />
        </button>

        <button
          type="button"
          className={editor.isActive("italic") ? "is-active" : ""}
          onClick={() => editor.chain().focus().toggleItalic().run()}
          aria-label="Italique"
        >
          <Italic size={15} />
        </button>

        <button
          type="button"
          className={editor.isActive("heading", { level: 2 }) ? "is-active" : ""}
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
          aria-label="Titre"
        >
          <Heading2 size={15} />
        </button>

        <button
          type="button"
          className={editor.isActive("bulletList") ? "is-active" : ""}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          aria-label="Liste à puces"
        >
          <List size={15} />
        </button>

        <button
          type="button"
          className={editor.isActive("orderedList") ? "is-active" : ""}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          aria-label="Liste numérotée"
        >
          <ListOrdered size={15} />
        </button>

        <button
          type="button"
          className={editor.isActive("blockquote") ? "is-active" : ""}
          onClick={() => editor.chain().focus().toggleBlockquote().run()}
          aria-label="Citation"
        >
          <Quote size={15} />
        </button>

        <span className="tiptap-toolbar-divider" />

        <button
          type="button"
          onClick={() => editor.chain().focus().undo().run()}
          aria-label="Annuler"
        >
          <Undo2 size={15} />
        </button>

        <button
          type="button"
          onClick={() => editor.chain().focus().redo().run()}
          aria-label="Rétablir"
        >
          <Redo2 size={15} />
        </button>
      </div>

      <EditorContent editor={editor} className="tiptap-editor-content" />
    </div>
  );
}
