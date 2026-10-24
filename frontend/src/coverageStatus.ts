// One definition of "done" for the Coverage page. Sign-offs decide coverage
// (the backend's rule); live Shopify data is evidence that can disagree.
import type { CoverageProduct } from './types';

export function isDone(p: CoverageProduct): boolean {
  return p.variations_complete && p.in_shopify;
}

/** Signed off as on Shopify, but the live store shows AI images missing. */
export function shopifyDisagrees(p: CoverageProduct): boolean {
  return p.in_shopify && p.on_shopify === false;
}
