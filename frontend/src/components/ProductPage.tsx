// One product: a cell per variant (rows = wood/colour, columns = front style).
// A cell shows the AI image live on Shopify, else the image generated here
// but not uploaded yet, else stays blank. Click any image to zoom in.
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import type { CatalogProduct, CatalogVariant } from '../types';
import * as api from '../api';
import { useDispatch } from '../context/ProjectsContext';
import { showError } from '../notify';
import ImageViewer, { type ViewerImage } from './ImageViewer';
import Segmented from './Segmented';
import CellBar from './CellBar';

type RowOrder = 'sales' | 'shopify';

// Both Shopify's CDN and our image route resize on ?width=; grids don't need full size.
function thumb(url: string): string {
  return `${url}${url.includes('?') ? '&' : '?'}width=480`;
}

function cellImage(v: CatalogVariant, small: boolean): string | null {
  const url = v.cell === 'live' ? v.shopify_image : v.cell === 'generated' ? v.local?.url : null;
  if (!url) return null;
  return small ? thumb(url) : url;
}

function cellLabel(v: CatalogVariant): string {
  if (v.cell === 'live') return 'On Shopify';
  if (v.cell === 'generated') {
    const verdict = v.local?.verdict === 'approved' ? ', approved' : v.local?.verdict === 'rejected' ? ', rejected' : '';
    return `Generated, not on Shopify${verdict}`;
  }
  return v.image_state === 'shared' ? 'No AI image (old photo)' : 'No image';
}

function caption(v: CatalogVariant): string {
  const name = v.style ? `${v.material} · ${v.style}` : v.material;
  return `${name} — ${cellLabel(v)} · ${v.units.toLocaleString()} sold`;
}

export default function ProductPage() {
  const { handle = '' } = useParams();
  const [product, setProduct] = useState<CatalogProduct | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [order, setOrder] = useState<RowOrder>('sales');
  const [viewing, setViewing] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);
  const navigate = useNavigate();
  const dispatch = useDispatch();

  useEffect(() => {
    setProduct(null);
    setError(null);
    api
      .getCatalogProduct(handle)
      .then(setProduct)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load product'));
  }, [handle]);

  const grid = useMemo(() => (product ? buildGrid(product.variants, order) : null), [product, order]);

  // Viewer walks every filled cell in on-screen order.
  const viewable = useMemo(
    () => (grid ? grid.rows.flatMap((row) => row.cells).filter((v): v is CatalogVariant => !!v && !!cellImage(v, false)) : []),
    [grid],
  );
  const viewerImages: ViewerImage[] = useMemo(
    () => viewable.map((v) => ({ src: cellImage(v, false) as string, caption: caption(v) })),
    [viewable],
  );

  if (error) return <div className="status-error">{error}</div>;
  if (!product || !grid) return <div className="status-info">Loading…</div>;

  // Named after the listing, so the catalog links the new door back to this product.
  const startDoor = async () => {
    setStarting(true);
    try {
      const p = await api.createProject(product.title, product.product_type, product.material_type);
      dispatch({ type: 'ADD_PROJECT', project: p });
      navigate(`/doors/${p.id}`);
    } catch (err) {
      showError("Couldn't create a door", err);
      setStarting(false);
    }
  };

  const open = (v: CatalogVariant) => {
    const i = viewable.indexOf(v);
    if (i >= 0) setViewing(i);
  };

  return (
    <div className="page">
      <Link to="/products" className="back-link">
        ← Products
      </Link>
      <header className="page-header">
        <div>
          <h1>{product.title}</h1>
          <div className="product-meta">
            {product.category_label} · {product.units ? `${product.units.toLocaleString()} sold` : 'no sales'}
            {product.other_units > 0 && (
              <span title="Those variants were deleted from the listing, so their sales can't be shown per cell.">
                {' '}
                (incl. {product.other_units.toLocaleString()} sold on variants since removed)
              </span>
            )}
          </div>
        </div>
        <div className="product-links">
          <a href={product.admin_url} target="_blank" rel="noreferrer">
            Open in Shopify
          </a>
          {product.project_id ? (
            <Link
              to={`/doors/${product.project_id}`}
              className="button-link primary"
              title={`Upload, learn the style and generate in "${product.project_name}"`}
            >
              Open door workspace
            </Link>
          ) : (
            <button type="button" className="primary" onClick={startDoor} disabled={starting}>
              {starting ? 'Creating…' : 'Start a door'}
            </button>
          )}
        </div>
      </header>

      <div className="product-summary">
        <CellBar live={product.live} generated={product.generated} missing={product.missing} />
        <span>
          <span className="legend legend--live">{product.live} on Shopify</span>
          <span className="legend legend--generated">{product.generated} generated, not uploaded</span>
          <span className="legend legend--missing">{product.missing} no image</span>
        </span>
        {grid.rows.length > 1 && (
          <Segmented<RowOrder>
            value={order}
            onChange={setOrder}
            options={[
              ['sales', 'Best sellers first'],
              ['shopify', 'Shopify order'],
            ]}
          />
        )}
      </div>
      {!product.project_id && (
        <div className="status-info products-notice">
          No door for this product yet. Start one to upload the sample photo and generate its variants.
        </div>
      )}

      {grid.styles.length > 0 ? (
        <div className="variant-matrix" style={{ gridTemplateColumns: `minmax(9rem, 12rem) repeat(${grid.styles.length}, minmax(10rem, 18rem))` }}>
          <div />
          {grid.styles.map((s) => (
            <div key={s} className="variant-matrix-head">
              {s}
            </div>
          ))}
          {grid.rows.map((row) => (
            <RowCells key={row.material} row={row} onOpen={open} />
          ))}
        </div>
      ) : (
        <div className="variant-grid">
          {grid.rows.map((row) => (
            <VariantCell key={row.material} variant={row.cells[0]!} title={row.material} onOpen={open} />
          ))}
        </div>
      )}

      {viewing !== null && (
        <ImageViewer images={viewerImages} index={viewing} onIndexChange={setViewing} onClose={() => setViewing(null)} />
      )}
    </div>
  );
}

interface Row {
  material: string;
  units: number;
  cells: (CatalogVariant | null)[]; // one per style column (or a single cell)
}

function buildGrid(variants: CatalogVariant[], order: RowOrder): { styles: string[]; rows: Row[] } {
  const styles = [...new Set(variants.map((v) => v.style).filter((s): s is string => !!s))];
  const byMaterial = new Map<string, CatalogVariant[]>();
  for (const v of variants) byMaterial.set(v.material, [...(byMaterial.get(v.material) ?? []), v]);
  const rows = [...byMaterial].map(([material, vs]) => ({
    material,
    units: vs.reduce((n, v) => n + v.units, 0),
    cells: styles.length ? styles.map((s) => vs.find((v) => v.style === s) ?? null) : [vs[0]],
  }));
  if (order === 'sales') rows.sort((a, b) => b.units - a.units);
  return { styles, rows };
}

function RowCells({ row, onOpen }: { row: Row; onOpen: (v: CatalogVariant) => void }) {
  return (
    <>
      <div className="variant-matrix-row">
        <strong>{row.material}</strong>
        <span className="muted">{row.units ? `${row.units.toLocaleString()} sold` : 'no sales'}</span>
      </div>
      {row.cells.map((v, i) =>
        v ? (
          <VariantCell key={v.id} variant={v} onOpen={onOpen} />
        ) : (
          <div key={i} className="variant-cell variant-cell--none" title="Not offered on Shopify">
            not offered
          </div>
        ),
      )}
    </>
  );
}

function VariantCell({ variant: v, title, onOpen }: { variant: CatalogVariant; title?: string; onOpen: (v: CatalogVariant) => void }) {
  const src = cellImage(v, true);
  return (
    <div className={`variant-cell variant-cell--${v.cell}`}>
      {src ? (
        <button type="button" className="variant-cell-image zoomable" onClick={() => onOpen(v)} aria-label={`Zoom ${caption(v)}`}>
          <img src={src} alt={caption(v)} loading="lazy" />
        </button>
      ) : (
        <div className="variant-cell-image variant-cell-blank" />
      )}
      <div className="variant-cell-info">
        {title && <strong className="variant-cell-title">{title}</strong>}
        <span className={`variant-cell-tag variant-cell-tag--${v.local?.verdict === 'rejected' && v.cell === 'generated' ? 'rejected' : v.cell}`}>
          {cellLabel(v)}
        </span>
        <span className="muted">{v.units ? `${v.units.toLocaleString()} sold` : '—'}</span>
      </div>
    </div>
  );
}
