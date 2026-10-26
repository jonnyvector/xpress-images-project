// "Shopify synced 5 min ago", or null when there is no usable sync time.
export function syncedAgo(iso: string | null): string | null {
  const syncedAt = iso ? new Date(iso) : null;
  if (!syncedAt || Number.isNaN(syncedAt.getTime())) return null;
  const mins = Math.round((Date.now() - syncedAt.getTime()) / 60000);
  if (mins < 1) return 'Shopify synced just now';
  if (mins < 60) return `Shopify synced ${mins} min ago`;
  if (mins < 60 * 24) return `Shopify synced ${Math.round(mins / 60)} h ago`;
  return `Shopify synced ${syncedAt.toLocaleDateString()}`;
}
