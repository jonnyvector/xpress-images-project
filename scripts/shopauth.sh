#!/usr/bin/env bash
# Log the Shopify CLI into the store (opens a browser) so Coverage's
# "Refresh from Shopify" can read products. Read-only access.
# Usage: scripts/shopauth.sh [store-subdomain]   (default: bcr-cabinets)
set -euo pipefail
shopify store auth --store "${1:-bcr-cabinets}.myshopify.com" --scopes read_products
