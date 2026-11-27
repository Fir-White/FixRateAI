export function localEditorOrigin(url: string | undefined) {
  if (!url || !/^http:\/\/127\.0\.0\.1(?::\d+)?$/.test(window.location.origin)) return '';
  try {
    const origin = new URL(url);
    if (origin.protocol === 'http:' && origin.hostname === 'localhost' && !origin.username && !origin.password) {
      return origin.origin;
    }
  } catch { /* An unavailable editor must not block downloads. */ }
  return '';
}
