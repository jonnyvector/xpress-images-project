import { useEffect, useCallback, useState } from 'react';
import { useProjects, useDispatch } from '../context/ProjectsContext';
import * as api from '../api';
import TabBar from './TabBar';
import ProjectTab from './ProjectTab';
import DoorLibrary from './DoorLibrary';

export default function Layout() {
  const { projects, openTabIds, activeProjectId } = useProjects();
  const openProjects = projects.filter((p) => openTabIds.includes(p.id));
  const dispatch = useDispatch();
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('gemini_api_key') ?? '');
  const [activeView, setActiveView] = useState<'library' | 'project'>('project');

  const handleApiKeyChange = useCallback((value: string) => {
    setApiKey(value);
    localStorage.setItem('gemini_api_key', value);
  }, []);

  // Load projects on mount
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        let list = await api.listProjects();
        if (list.length === 0) {
          const p = await api.createProject('Door 1', 'Cabinet Door');
          list = [p];
        }
        if (!cancelled) dispatch({ type: 'SET_PROJECTS', projects: list });
      } catch (err) {
        console.error('Failed to load projects:', err);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [dispatch]);

  const handleAddProject = useCallback(async () => {
    try {
      const name = `Door ${projects.length + 1}`;
      const p = await api.createProject(name, 'Cabinet Door');
      dispatch({ type: 'ADD_PROJECT', project: p });
    } catch (err) {
      console.error('Failed to create project:', err);
    }
  }, [dispatch, projects.length]);

  const handleCloseTab = useCallback((id: string) => {
    dispatch({ type: 'CLOSE_TAB', id });
  }, [dispatch]);

  const handleResetAll = useCallback(async () => {
    try {
      for (const p of projects) {
        await api.deleteProject(p.id);
      }
      const p = await api.createProject('Door 1', 'Cabinet Door');
      dispatch({ type: 'SET_PROJECTS', projects: [p] });
    } catch (err) {
      console.error('Failed to reset:', err);
    }
  }, [dispatch, projects]);

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <h2>Settings</h2>
        <div className="form-group">
          <label htmlFor="api-key">Gemini API Key</label>
          <input
            id="api-key"
            type="password"
            value={apiKey}
            onChange={(e) => handleApiKeyChange(e.target.value)}
            placeholder="Enter your API key"
          />
        </div>
        {!apiKey && (
          <div className="status-info">Enter your API key to enable generation</div>
        )}
        <div style={{ marginTop: 'auto' }}>
          <button className="danger" onClick={handleResetAll} style={{ width: '100%' }}>
            Reset All
          </button>
        </div>
      </aside>
      <div className="main-content">
        <div className="top-bar">
          <TabBar
            projects={openProjects}
            activeId={activeProjectId}
            activeView={activeView}
            onSelect={(id) => {
              dispatch({ type: 'SET_ACTIVE', id });
              setActiveView('project');
            }}
            onClose={handleCloseTab}
            onSelectLibrary={() => setActiveView('library')}
          />
          <button onClick={handleAddProject}>+ Add New Door</button>
        </div>
        <div className="content-area">
          {activeView === 'library' ? (
            <DoorLibrary
              projects={projects}
              onSelectProject={(id) => {
                dispatch({ type: 'OPEN_TAB', id });
                setActiveView('project');
              }}
            />
          ) : openProjects.length === 0 ? (
            <div className="status-info">No project selected</div>
          ) : (
            openProjects.map((p) => (
              <div
                key={p.id}
                style={{ display: p.id === activeProjectId ? 'block' : 'none' }}
              >
                <ProjectTab project={p} apiKey={apiKey} />
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
