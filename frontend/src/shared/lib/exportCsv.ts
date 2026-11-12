/** Quote values and prevent spreadsheet apps from interpreting input as a formula. */
export function csvCell(value: string | null): string {
  const text = value ?? "";
  const safe = /^[\u0000-\u0020]*[=+\-@]/.test(text) ? `'${text}` : text;
  return `"${safe.replace(/"/g, '""')}"`;
}
