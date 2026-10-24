// Door names are usually upload filenames ("adobe_5-piece_maple_select").
// Show them readably; the raw name stays available as a tooltip.
export function displayName(raw: string): string {
  const spaced = raw.replace(/_+/g, ' ').replace(/\s+/g, ' ').trim();
  if (!spaced) return raw;
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Placeholder name for a door created with "+ New door", until an image is uploaded. */
export const NEW_DOOR_NAME = 'New door';
