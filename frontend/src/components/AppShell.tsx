// App frame: left navigation (main views, recent doors, settings) and the
// routed page. Loads the project list once for every page.
import { useCallback, useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router';
import { useDispatch, useProjects } from '../context/ProjectsContext';
import { useApiKey } from '../hooks/useApiKey';
import * as api from '../api';
import { showError } from '../notify';
import { displayName, NEW_DOOR_NAME } from '../doorNames';
import ReviewCountBadge from './ReviewCountBadge';
import ErrorToasts from './ErrorToasts';

const navClass = ({ isActive }: { isActive: boolean }) => `nav-link${isActive ? ' nav-link--active' : ''}`;

export default function AppShell() {
  const { projects, recentIds } = useProjects();
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [apiKey, setApiKey] = useApiKey();
  const [creating, setCreating] = useState(false);
  // Open the settings once if the key is missing; after that the user decides.
  const [settingsOpenAtStart] = useState(() => !apiKey);
  const atLibrary = useLocation().pathname.startsWith('/library');
  const listLoaded = useRef(false);

  // Load the list on start, then again on each return to the library so doors
  // that finished generating while you were elsewhere show their new state.
  useEffect(() => {
    if (listLoaded.current && !atLibrary) return;
    listLoaded.current = true;
    api
      .listProjects()
      .then((list) => dispatch({ type: 'SET_PROJECTS', projects: list }))
      .catch((err) => {
        dispatch({ type: 'LOAD_FAILED' });
        showError("Couldn't load doors", err);
      });
  }, [dispatch, atLibrary]);

  const handleNewDoor = useCallback(async () => {
    setCreating(true);
    try {
      const p = await api.createProject(NEW_DOOR_NAME, 'Cabinet Door');
      dispatch({ type: 'ADD_PROJECT', project: p });
      navigate(`/doors/${p.id}`);
    } catch (err) {
      showError("Couldn't create a door", err);
    } finally {
      setCreating(false);
    }
  }, [dispatch, navigate]);

  const byId = new Map(projects.map((p) => [p.id, p]));
  const recent = recentIds.map((id) => byId.get(id)).filter((p) => p !== undefined);

  return (
    <div className="app-layout">
      <nav className="sidebar" aria-label="Main">
        <div className="sidebar-brand">Door Images</div>
        <button type="button" className="primary sidebar-new" onClick={handleNewDoor} disabled={creating}>
          {creating ? 'Creating…' : '+ New door'}
        </button>

        <div className="nav-group">
          <NavLink to="/library" className={navClass}>
            Library
          </NavLink>
          <NavLink to="/review" className={navClass}>
            Review <ReviewCountBadge />
          </NavLink>
          <NavLink to="/products" className={navClass}>
            Products
          </NavLink>
          <NavLink to="/coverage" className={navClass}>
            Coverage
          </NavLink>
        </div>

        {recent.length > 0 && (
          <div className="nav-group">
            <div className="nav-heading">Recent doors</div>
            {recent.map((p) => (
              <div key={p.id} className="nav-recent">
                <NavLink to={`/doors/${p.id}`} className={navClass} title={p.name}>
                  {displayName(p.name)}
                </NavLink>
                <button
                  type="button"
                  className="nav-forget"
                  onClick={() => dispatch({ type: 'FORGET_RECENT', id: p.id })}
                  aria-label={`Remove ${p.name} from recent doors`}
                  title="Remove from this list (the door itself is kept)"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        <details className="sidebar-settings" open={settingsOpenAtStart}>
          <summary>Settings{!apiKey && <span className="nav-warn"> · API key needed</span>}</summary>
          <div className="form-group">
            <label htmlFor="api-key">Gemini API key</label>
            <input
              id="api-key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Needed to learn and generate"
            />
          </div>
        </details>
      </nav>

      <main className="main-content">
        <div className="content-area">
          <Outlet />
        </div>
      </main>
      <ErrorToasts />
    </div>
  );
}
