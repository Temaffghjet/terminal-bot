/** Коды причины входа из backend (check_entry reason при OPEN). */
const LABELS: Record<string, string> = {
  ema_long: "Лонг EMA",
  ema_short: "Шорт EMA",
};

/**
 * Человекочитаемая подпись; если кода нет в словаре — показываем как есть.
 */
export function formatEmaEntryReason(code: string | undefined | null): string {
  const c = String(code ?? "").trim();
  if (!c) return "—";
  return LABELS[c] ?? c;
}

/** Есть ли отдельная русская подпись (тогда на фронте можно дублировать код мелким шрифтом). */
export function emaEntryReasonHasMappedLabel(code: string | undefined | null): boolean {
  const c = String(code ?? "").trim();
  return c !== "" && c in LABELS;
}
