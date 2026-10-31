const DATE_FORMATTER = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

const SHORT_DATE_FORMATTER = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "short",
  timeZone: "UTC",
});

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Asia/Yekaterinburg",
});

const MONTH_FORMATTER = new Intl.DateTimeFormat("ru-RU", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

function asDate(value: string): Date {
  return value.length === 10 ? new Date(`${value}T00:00:00Z`) : new Date(value);
}

export function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  return DATE_FORMATTER.format(asDate(value));
}

export function formatShortDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  return SHORT_DATE_FORMATTER.format(asDate(value));
}

export function formatDateTime(value: string | null): string {
  if (!value) {
    return "—";
  }
  return DATE_TIME_FORMATTER.format(new Date(value));
}

export function formatMonth(year: number, month: number): string {
  return MONTH_FORMATTER.format(new Date(Date.UTC(year, month - 1, 1)));
}

export function formatDays(value: number): string {
  const absolute = Math.abs(value);
  const lastDigit = absolute % 10;
  const lastTwo = absolute % 100;
  const word =
    lastTwo >= 11 && lastTwo <= 14
      ? "дней"
      : lastDigit === 1
        ? "день"
        : lastDigit >= 2 && lastDigit <= 4
          ? "дня"
          : "дней";
  return `${absolute} ${word}`;
}

export function dateDifference(from: string, to: string): number {
  const fromTime = asDate(from).getTime();
  const toTime = asDate(to).getTime();
  return Math.round((toTime - fromTime) / 86_400_000);
}

export function pluralize(
  count: number,
  one: string,
  few: string,
  many: string,
): string {
  const lastDigit = count % 10;
  const lastTwo = count % 100;
  if (lastTwo >= 11 && lastTwo <= 14) {
    return many;
  }
  if (lastDigit === 1) {
    return one;
  }
  if (lastDigit >= 2 && lastDigit <= 4) {
    return few;
  }
  return many;
}
