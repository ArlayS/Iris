import "./casier-list.css";

import { Bot, Eye, Gavel, MegaphoneOff } from "lucide-react";

import { formatSanctionsSummary, plural } from "./formatters";

function count(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.floor(number) : 0;
}

function Metric({ tone, icon: Icon, label, value, unit = null, detail }) {
  return (
    <div className={`cz-metric cz-metric--${tone}`}>
      <dt className="cz-metric-label">
        <Icon size={16} aria-hidden="true" />
        {label}
      </dt>
      <dd className="cz-metric-value">
        <strong>{value.toLocaleString("fr-FR")}</strong>
        {unit && <span className="cz-metric-unit">{unit}</span>}
      </dd>
      <dd className="cz-metric-detail">{detail}</dd>
    </div>
  );
}

// Quatre compteurs du casier ouvert ; les rappels à l'ordre sont comptés à part (sans effet sur le statut).
export default function CasierMetrics({ casier }) {
  if (!casier) return null;

  const reminders = count(casier.rappels_count);
  const sanctions = Math.max(0, count(casier.sanctions_count) - reminders);
  const summary = formatSanctionsSummary(casier.sanctions_summary);
  const activeFiches = count(casier.active_fiches_s_count);
  const fiches = Array.isArray(casier.fiches_s) ? casier.fiches_s.length : null;
  const openFlags = count(casier.ai_flags_open);
  const totalFlags = Math.max(count(casier.ai_flags_total), openFlags);

  let fichesDetail = "Aucune fiche S active";
  if (fiches !== null) {
    fichesDetail = fiches > 0 ? `sur ${plural(fiches, "rédigée", "rédigées")}` : "Aucune fiche S rédigée";
  } else if (activeFiches > 0) {
    fichesDetail = "En cours de suivi";
  }

  return (
    <dl className="cz-metrics">
      <Metric
        tone="sanctions"
        icon={Gavel}
        label="Sanctions"
        value={sanctions}
        detail={summary || "Aucune sanction"}
      />
      <Metric
        tone="rappels"
        icon={MegaphoneOff}
        label="Rappels à l'ordre"
        value={reminders}
        detail="Sans effet sur le statut"
      />
      <Metric tone="fiches" icon={Eye} label="Fiches S actives" value={activeFiches} detail={fichesDetail} />
      <Metric
        tone="ia"
        icon={Bot}
        label="Signalements IA"
        value={openFlags}
        unit="à traiter"
        detail={totalFlags > 0 ? `sur ${totalFlags.toLocaleString("fr-FR")}` : "Aucun signalement"}
      />
    </dl>
  );
}
