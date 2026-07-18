export type SocialTimeLocale = "pt-BR" | "en-US";

export function formatSocialTimestamp(value?: string | number | null, locale: SocialTimeLocale = "pt-BR", nowValue: Date = new Date()) {
  const missing = locale === "en-US" ? "time unavailable" : "horário indisponível";
  if (value == null || value === "") return { label: missing, title: missing, dateTime: undefined };
  const numeric = typeof value === "number" || /^\d+(\.\d+)?$/.test(String(value).trim()) ? Number(value) : null;
  const parsed = new Date(numeric == null ? String(value) : numeric > 10_000_000_000 ? numeric : numeric * 1000);
  if (Number.isNaN(parsed.getTime())) return { label: missing, title: missing, dateTime: undefined };
  const sameDay = parsed.getFullYear() === nowValue.getFullYear()
    && parsed.getMonth() === nowValue.getMonth()
    && parsed.getDate() === nowValue.getDate();
  const time = new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit", hour12: true }).format(parsed);
  const date = new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", year: "numeric" }).format(parsed);
  const title = new Intl.DateTimeFormat(locale, { dateStyle: "full", timeStyle: "long" }).format(parsed);
  return { label: sameDay ? time : `${date} · ${time}`, title, dateTime: parsed.toISOString() };
}
