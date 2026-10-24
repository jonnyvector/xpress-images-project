import { createContext, useContext, useEffect, useReducer, type ReactNode, type Dispatch } from 'react';
import type { Project } from '../types';

interface ProjectsState {
  projects: Project[];
  loaded: boolean;
  // Doors opened lately, newest first. Shown in the sidebar for quick return.
  recentIds: string[];
}

type Action =
  | { type: 'SET_PROJECTS'; projects: Project[] }
  | { type: 'LOAD_FAILED' }
  | { type: 'ADD_PROJECT'; project: Project }
  | { type: 'UPDATE_PROJECT'; project: Project }
  | { type: 'VISIT'; id: string }
  | { type: 'FORGET_RECENT'; id: string };

const RECENT_KEY = 'recentDoorIds';
const LEGACY_TABS_KEY = 'openTabIds';
const MAX_RECENT = 8;

function loadRecent(): string[] {
  try {
    // One-time move from the old open-tabs list (removed once saveRecent runs).
    const stored = localStorage.getItem(RECENT_KEY) ?? localStorage.getItem(LEGACY_TABS_KEY);
    const ids: unknown = stored ? JSON.parse(stored) : [];
    if (!Array.isArray(ids)) return [];
    return ids.filter((id): id is string => typeof id === 'string').slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

function saveRecent(ids: string[]) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(ids));
    localStorage.removeItem(LEGACY_TABS_KEY);
  } catch {
    /* storage unavailable: recents just won't persist */
  }
}

function reducer(state: ProjectsState, action: Action): ProjectsState {
  switch (action.type) {
    case 'SET_PROJECTS': {
      const ids = new Set(action.projects.map((p) => p.id));
      // Doors are never deleted, so any door added while the list was in
      // flight (e.g. "+ New door") is kept rather than dropped.
      const added = state.projects.filter((p) => !ids.has(p.id));
      return {
        projects: [...action.projects, ...added],
        loaded: true,
        recentIds: state.recentIds.filter((id) => ids.has(id) || added.some((p) => p.id === id)),
      };
    }
    case 'LOAD_FAILED':
      // Stop showing "Loading…" forever; pages render empty and the error toast explains.
      return { ...state, loaded: true };
    case 'ADD_PROJECT':
      return { ...state, projects: [...state.projects, action.project] };
    case 'UPDATE_PROJECT': {
      // Upsert: a door opened by link before (or without) the list loading.
      const known = state.projects.some((p) => p.id === action.project.id);
      return {
        ...state,
        projects: known
          ? state.projects.map((p) => (p.id === action.project.id ? action.project : p))
          : [...state.projects, action.project],
      };
    }
    case 'VISIT': {
      if (state.recentIds[0] === action.id) return state;
      const rest = state.recentIds.filter((id) => id !== action.id);
      return { ...state, recentIds: [action.id, ...rest].slice(0, MAX_RECENT) };
    }
    case 'FORGET_RECENT':
      return { ...state, recentIds: state.recentIds.filter((id) => id !== action.id) };
  }
}

const ProjectsContext = createContext<ProjectsState>({ projects: [], loaded: false, recentIds: [] });
const DispatchContext = createContext<Dispatch<Action>>(() => {});

export function ProjectsProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, () => ({
    projects: [],
    loaded: false,
    recentIds: loadRecent(),
  }));

  useEffect(() => {
    saveRecent(state.recentIds);
  }, [state.recentIds]);

  return (
    <ProjectsContext.Provider value={state}>
      <DispatchContext.Provider value={dispatch}>{children}</DispatchContext.Provider>
    </ProjectsContext.Provider>
  );
}

export function useProjects() {
  return useContext(ProjectsContext);
}

export function useDispatch() {
  return useContext(DispatchContext);
}
