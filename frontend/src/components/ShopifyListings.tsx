// Live Shopify AI-image status for one coverage row: a compact badge for the
// table cell and a detail block for the expanded row.
import type { CoverageProduct, ShopifyListing } from '../types';
import { activeListings, isDone } from '../coverageStatus';

export function ShopifyBadge({ product }: { product: CoverageProduct }) {
  const listings = activeListings(product);
  if (listings.length === 0) return <span className="shopify-status shopify-status--none">Not found on Shopify</span>;
  // Summed across every matched listing, so one finished listing can't hide another.
  const total = listings.reduce((n, l) => n + l.variant_count, 0);
  const ok = listings.reduce((n, l) => n + l.own_image_count, 0);
  if (isDone(product)) {
    return <span className="shopify-status shopify-status--done">✓ All {total} variants have their own image</span>;
  }
  if (ok === 0) return <span className="shopify-status shopify-status--empty">None of {total} variants has its own image</span>;
  const lacking = listings.flatMap((l) => [...l.missing_variants, ...l.shared_variants]);
  const shown = lacking.slice(0, 2).join(', ') + (lacking.length > 2 ? ` +${lacking.length - 2} more` : '');
  return (
    <span className="shopify-status shopify-status--partial" title={lacking.join('\n')}>
      {total - ok} of {total} need their own image <span className="shopify-status-names">· {shown}</span>
    </span>
  );
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
              {l.own_image_count}/{l.variant_count} variants have their own image
            </span>
          </div>
          {l.missing_variants.length > 0 && <WoodList label="No image" woods={l.missing_variants} />}
          {l.shared_variants.length > 0 && (
            <WoodList label="Old photo shared with many variants" woods={l.shared_variants} warn />
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
