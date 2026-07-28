import { useEffect } from "react";
import { EditorContent, useEditor, BubbleMenu } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import Table from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import Image from "@tiptap/extension-image";
import Link from "@tiptap/extension-link";
import TextAlign from "@tiptap/extension-text-align";
import Underline from "@tiptap/extension-underline";
import TextStyle from "@tiptap/extension-text-style";
import Color from "@tiptap/extension-color";
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
  Underline as UnderlineIcon,
  Table as TableIcon,
  Link as LinkIcon,
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
      Table.configure({ resizable: true }),
      TableRow,
      TableCell,
      TableHeader,
      Image,
      Link.configure({ openOnClick: false }),
      TextAlign.configure({ types: ["heading", "paragraph"] }),
      Underline,
      TextStyle,
      Color,
    ],
    content: safeValue,
    autofocus: autoFocus ? "end" : false,
    immediatelyRender: false,
    onUpdate: ({ editor: current }) => {
      try {
        onChange(current.storage.markdown.getMarkdown());
      } catch (err) {
        console.error("Erreur markdown:", err);
      }
    },
  });

  useEffect(() => {
    if (!editor) return;
    try {
      const currentMarkdown = editor.storage.markdown.getMarkdown();
      if (safeValue !== currentMarkdown) {
        editor.commands.setContent(safeValue, false);
      }
    } catch (err) {
      console.error("Erreur setContent:", err);
    }
  }, [editor, safeValue]);

  if (!editor) return null;

  return (
    <div className="tiptap-editor">
      <div className="tiptap-toolbar">
        <button type="button" className={editor.isActive("bold") ? "is-active" : ""} onClick={() => editor.chain().focus().toggleBold().run()}><Bold size={15} /></button>
        <button type="button" className={editor.isActive("italic") ? "is-active" : ""} onClick={() => editor.chain().focus().toggleItalic().run()}><Italic size={15} /></button>
        <button type="button" className={editor.isActive("underline") ? "is-active" : ""} onClick={() => editor.chain().focus().toggleUnderline().run()}><UnderlineIcon size={15} /></button>
        <button type="button" className={editor.isActive("heading", { level: 2 }) ? "is-active" : ""} onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}><Heading2 size={15} /></button>
        <button type="button" className={editor.isActive("bulletList") ? "is-active" : ""} onClick={() => editor.chain().focus().toggleBulletList().run()}><List size={15} /></button>
        <button type="button" className={editor.isActive("orderedList") ? "is-active" : ""} onClick={() => editor.chain().focus().toggleOrderedList().run()}><ListOrdered size={15} /></button>
        <button type="button" className={editor.isActive("blockquote") ? "is-active" : ""} onClick={() => editor.chain().focus().toggleBlockquote().run()}><Quote size={15} /></button>
        <button type="button" onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}><TableIcon size={15} /></button>
        <button type="button" onClick={() => { const url = window.prompt("URL du lien:"); if (url) editor.chain().focus().setLink({ href: url }).run(); }}><LinkIcon size={15} /></button>
        <span className="tiptap-toolbar-divider" />
        
