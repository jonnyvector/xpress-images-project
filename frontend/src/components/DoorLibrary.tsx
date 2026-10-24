// The door library. Main doors (each product's canonical door, from Coverage)
// come first under their product name; experiments and older attempts sit
// behind "Other versions". Search always covers every door.
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import type { Project } from '../types';
import * as api from '../api';
import { useDispatch, useProjects } from '../context/ProjectsContext';
import { showError } from '../notify';
import { displayName } from '../doorNames';
import { needsAttention } from '../doorStatus';
import LibraryCard from './LibraryCard';
import Segmented from './Segmented';

type Show = 'main' | 'attention' | 'all';
type Kind = 'all' | Project['product_type'];
type Material = 'all' | Project['material_type'];
const PAGE = 60;

// Which doors are main doors comes from Coverage. Kept between visits so the
// library shows at once on return; refreshed in the background each time.
let mainDoorsCache: Map<string, string> | null = null;

export default function DoorLibrary() {
  const { projects, loaded } = useProjects();
  const dispatch = useDispatch();
  const navigate = useNavigate();
  // Filters live in the URL so Back from a door returns to the same view.
  const [params, setParams] = useSearchParams();
  const show = (params.get('show') as Show | null) ?? 'main';
  const kind = (params.get('kind') as Kind | null) ?? 'all';
  const material = (params.get('material') as Material | null) ?? 'all';
  const query = params.get('q') ?? '';
  const setParam = (key: string, value: string, fallback: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value === fallback) next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true },
    );
  const setShow = (v: Show) => setParam('show', v, 'main');
  const setKind = (v: Kind) => setParam('kind', v, 'all');
  const setMaterial = (v: Material) => setParam('material', v, 'all');
  const setQuery = (v: string) => setParam('q', v, '');
  const [limit, setLimit] = useState(PAGE);
  // project id -> product title for each product's canonical door, in sales order
  const [mainDoors, setMainDoors] = useState<Map<string, string> | null>(mainDoorsCache);

  useEffect(() => {
    api
      .getCoverage()
      .then((cov) => {
        const map = new Map<string, string>();
        for (const cat of cov.categories) {
          for (const p of cat.products) {
            if (p.canonical_project_id && !map.has(p.canonical_project_id)) {
              map.set(p.canonical_project_id, p.title);
            }
          }
        }
        mainDoorsCache = map;
        setMainDoors(map);
      })
      .catch((err) => {
        setMainDoors((prev) => prev ?? new Map());
        showError("Couldn't load which doors are main doors", err);
      });
  }, []);

  useEffect(() => setLimit(PAGE), [show, kind, material, query]);

  const rename = async (id: string, name: string) => {
    try {
      const updated = await api.updateProject(id, { name });
      dispatch({ type: 'UPDATE_PROJECT', project: updated });
      return true;
    } catch (err) {
      showError("Couldn't rename door", err);
      return false;
    }
  };

  const searching = query.trim().length > 0;

  const visible = useMemo(() => {
    const mains = mainDoors ?? new Map<string, string>();
    const rank = new Map([...mains.keys()].map((id, i) => [id, i]));
    const q = query.trim().toLowerCase();
    const items = projects.filter((p) => {
      if (kind !== 'all' && p.product_type !== kind) return false;
      if (material !== 'all' && p.material_type !== material) return false;
      if (q) {
        const text = `${p.name} ${displayName(p.name)} ${mains.get(p.id) ?? ''} ${p.door_style ?? ''}`;
        return text.toLowerCase().includes(q);
      }
      if (show === 'main') return mains.has(p.id);
      if (show === 'attention') return needsAttention(p);
      return true;
    });
    // Main doors keep Coverage's sales order and lead; everything else by name.
    return items.sort((a, b) => {
      const ra = rank.get(a.id) ?? Infinity;
      const rb = rank.get(b.id) ?? Infinity;
      if (ra !== rb) return ra - rb;
      return displayName(a.name).localeCompare(displayName(b.name));
    });
  }, [projects, mainDoors, kind, material, query, show]);

  if (!loaded || mainDoors === null) return <div className="status-info">Loading library…</div>;

  const counts = {
    main: projects.filter((p) => mainDoors.has(p.id)).length,
    attention: projects.filter(needsAttention).length,
    all: projects.length,
  };

  return (
    <div className="page">
      <header className="page-header">
        <h1>Library</h1>
        <input
          type="search"
          className="library-search"
          placeholder="Search every door by name or product…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </header>

      <div className="library-toolbar">
        <Segmented
          value={searching ? null : show}
          onChange={setShow}
          options={[
            ['main', `Main doors (${counts.main})`],
            ['attention', `Needs attention (${counts.attention})`],
            ['all', `All (${counts.all})`],
          ]}
        />
        <Segmented
          value={kind}
          onChange={setKind}
          options={[
            ['all', 'Doors & fronts'],
            ['Cabinet Door', 'Doors'],
            ['Drawer Front', 'Drawer fronts'],
          ]}
        />
        <Segmented
          value={material}
          onChange={setMaterial}
          options={[
            ['all', 'Any material'],
            ['wood', 'Wood'],
            ['rtf', 'Thermofoil'],
          ]}
        />
      </div>

      {searching && <div className="library-hint">Searching all {counts.all} doors</div>}

      {visible.length === 0 ? (
        <div className="status-info">
          {!searching && show === 'main'
            ? "No main doors yet. A product's main door is chosen on the Coverage page."
            : 'No doors match.'}
        </div>
      ) : (
        <>
          <div className="library-grid">
            {visible.slice(0, limit).map((p) => (
              <LibraryCard
                key={p.id}
                project={p}
                productTitle={mainDoors.get(p.id)}
                onOpen={(id) => navigate(`/doors/${id}`)}
                onRename={rename}
              />
            ))}
          </div>
          {visible.length > limit && (
            <button type="button" className="library-more" onClick={() => setLimit((n) => n + PAGE)}>
              Show more ({visible.length - limit} left)
            </button>
          )}
        </>
      )}

      {!searching && show === 'main' && counts.all > counts.main && (
        <button type="button" className="link-button library-others" onClick={() => setShow('all')}>
          Show the {counts.all - counts.main} other versions and experiments
        </button>
      )}
    </div>
  );
}
