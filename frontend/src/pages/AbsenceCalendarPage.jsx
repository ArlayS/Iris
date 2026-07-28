import { useMemo, useState } from "react";
import {
  addDays,
  addMonths,
  endOfMonth,
  endOfWeek,
  format,
  isBefore,
  isSameDay,
  isSameMonth,
  isWithinInterval,
  parseISO,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { fr } from "date-fns/locale";
import { ChevronLeft, ChevronRight, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";

const WEEKDAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

function toIsoDate(date) {
  return format(date, "yyyy-MM-dd");
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export default function AbsenceCalendarPage() {
  const [absences, setAbsences] = useState([]);
  const [loading, setLoading] = useState(true);
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [selection, setSelection] = useState(null); // { start, end }
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const loadAbsences = async () => {
    try {
      const response = await api.get("/staff/absences");
      setAbsences(response.data);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useState(() => {
    loadAbsences();
  }, []);

  const days = useMemo(() => {
    const start = startOfWeek(startOfMonth(currentMonth), { weekStartsOn: 1 });
    const end = endOfWeek(endOfMonth(currentMonth), { weekStartsOn: 1 });
    const result = [];
    let cursor = start;
    while (cursor <= end) {
      result.push(cursor);
      cursor = addDays(cursor, 1);
    }
    return result;
  }, [currentMonth]);

  const absencesByDay = useMemo(() => {
    const map = new Map();
    for (const entry of absences) {
      const start = parseISO(entry.start_date);
      const end = parseISO(entry.end_date);
      for (const day of days) {
        if (isWithinInterval(day, { start, end }) || isSameDay(day, start) || isSameDay(day, end)) {
          const key = toIsoDate(day);
          if (!map.has(key)) map.set(key, []);
          map.get(key).push(entry);
        }
      }
    }
    return map;
  }, [absences, days]);

  const handleDayClick = (day) => {
    if (!selection || !selection.start) {
      setSelection({ start: day, end: day });
      return;
    }
    if (isBefore(day, selection.start)) {
      setSelection({ start: day, end: day });
      return;
    }
    setSelection({ start: selection.start, end: day });
  };

  const clearSelection = () => {
    setSelection(null);
    setReason("");
  };

  const submitAbsence = async () => {
    if (!selection) return;
    setSubmitting(true);
    try {
      const response = await api.post("/staff/absences", {
        start_date: toIsoDate(selection.start),
        end_date: toIsoDate(selection.end),
