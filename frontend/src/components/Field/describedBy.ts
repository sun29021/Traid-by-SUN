/** ids of a field's helper/error texts, for the control's aria-describedby. */
export function describedBy(id: string, helper?: string, error?: string): string | undefined {
  const ids = [helper ? `${id}-helper` : null, error ? `${id}-error` : null].filter(Boolean);
  return ids.length ? ids.join(' ') : undefined;
}
