// Coverage is decided by Shopify alone: a product is done when every variant
// its live listing(s) hold has its own image (backend/shopify_live.py).
import type { CoverageProduct } from './types';

export function activeListings(p: CoverageProduct) {
  return p.shopify_listings.filter((l) => l.status === 'ACTIVE');
}

export function isDone(p: CoverageProduct): boolean {
  const listings = activeListings(p);
  return listings.length > 0 && listings.every((l) => l.fully_imaged);
}
