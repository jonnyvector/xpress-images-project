// Live Shopify AI-image status for one coverage row: a compact badge for the
// table cell and a detail block for the expanded row.
import type { CoverageProduct, ShopifyListing } from '../types';

export function ShopifyBadge({ product }: { product: CoverageProduct }) {
  const listings = product.shopify_listings;
  // Your own sign-off always shows; the live count sits beside it.
  const signedOff = product.in_shopify ? <span className="badge badge-approved">Signed off</span> : null;
  if (listings.length > 0) {
    // Summed across every matched listing, so one finished listing can't hide another.
    const ai = listings.reduce((n, l) => n + l.ai_wood_count, 0);
    const total = listings.reduce((n, l) => n + l.wood_count, 0);
    const done = listings.every((l) => l.fully_imaged);
    const cls = done ? 'badge-approved' : ai > 0 ? 'badge-partial' : 'badge-warn';
    const wrong = listings.some((l) => l.mismatched_woods.length > 0);
    return (
      <span className="shopify-badges">
        {signedOff}
        <span className={`badge ${cls}`} title={wrong ? 'Some woods show an image of a different wood' : undefined}>
          AI {ai}/{total}
          {wrong && ' ⚠'}
        </span>
      </span>
    );
  }
  // No live data for this row: fall back to the manual / CSV signals.
  if (signedOff) return signedOff;
  if (product.on_shopify === true) {
    return <span className="badge badge-approved">On Shopify</span>;
  }
  if (product.on_shopify === false) return <span className="badge badge-warn">Missing images</span>;
  return <span className="badge badge-muted">—</span>;
}

export function ShopifyDetail({ listings, adminUrl }: { listings: ShopifyListing[]; adminUrl: string | null }) {
  if (listings.length === 0) return null;
  return (
    <div className="shopify-detail">
      {listings.map((l) => (
        <div key={l.handle} className="shopify-listing">
          <div className="shopify-listing-head">
            {adminUrl ? (
              <a href={`${adminUrl}?query=${encodeURIComponent(l.handle)}`} target="_blank" rel="noreferrer">
                {l.title}
              </a>
            ) : (
              l.title
            )}
            {l.status !== 'ACTIVE' && <span className="badge badge-muted">{l.status.toLowerCase()}</span>}
            <span className="shopify-listing-count">
              {l.ai_wood_count}/{l.wood_count} woods have AI images
            </span>
          </div>
          {l.missing_woods.length > 0 && (
            <WoodList label="Missing AI image" woods={l.missing_woods} />
          )}
          {l.mismatched_woods.length > 0 && (
            <WoodList label="Shows a different wood's image" woods={l.mismatched_woods} warn />
          )}
        </div>
      ))}
    </div>
  );
}

function WoodList({ label, woods, warn = false }: { label: string; woods: string[]; warn?: boolean }) {
  return (
    <div className="shopify-woods">
      <span className="shopify-woods-label">{label}:</span>
      {woods.map((w) => (
        <span key={w} className={`wood-chip ${warn ? 'wood-chip--warn' : ''}`}>
          {w}
        </span>
      ))}
    </div>
  );
}
