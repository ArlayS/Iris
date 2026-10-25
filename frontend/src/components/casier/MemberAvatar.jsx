import { useEffect, useState } from "react";
import { UserRound } from "lucide-react";

const TONES = ["sage", "blue", "violet"];

function initialOf(name) {
  const first = Array.from(String(name || "").trim())[0] || "";
  const isLetter = first.toLowerCase() !== first.toUpperCase();
  return isLetter || /\d/.test(first) ? first.toUpperCase() : "";
}

function toneOf(seed) {
  const text = String(seed || "");
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) % 997;
  }
  return TONES[hash % TONES.length];
}

function safeAvatarUrl(url) {
  return typeof url === "string" && /^https?:\/\//i.test(url) ? url : null;
}

// Décoratif (aria-hidden) : le nom du membre est toujours écrit à côté.
export default function MemberAvatar({ member, size = 40, shape = "circle", className = "" }) {
  const url = safeAvatarUrl(member?.avatar_url);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [url]);

  const name = member?.display_name || member?.username || "";
  const initial = initialOf(name);
  const tone = toneOf(member?.id || name);
  const classes = ["cz-avatar", tone !== "sage" ? `cz-avatar--${tone}` : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <span
      className={classes}
      style={{
        width: size,
        height: size,
        borderRadius: shape === "square" ? Math.round(size * 0.31) : "50%",
        fontSize: Math.max(11, Math.round(size * 0.4)),
      }}
      aria-hidden="true"
    >
      {url && !failed ? (
        <img
          src={url}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
      ) : initial ? (
        initial
      ) : (
        <UserRound size={Math.round(size * 0.5)} />
      )}
    </span>
  );
}
