import { createContext, useContext, useReducer, type ReactNode, type Dispatch } from 'react';
import type { Project } from '../types';

interface ProjectsState {
  projects: Project[];
  openTabIds: string[];
  activeProjectId: string | null;
}

type Action =
  | { type: 'SET_PROJECTS'; projects: Project[] }
  | { type: 'SET_ACTIVE'; id: string }
  | { type: 'ADD_PROJECT'; project: Project }
  | { type: 'UPDATE_PROJECT'; project: Project }
  | { type: 'REMOVE_PROJECT'; id: string }
  | { type: 'OPEN_TAB'; id: string }
  | { type: 'CLOSE_TAB'; id: string };

const OPEN_TABS_KEY = 'openTabIds';

function loadOpenTabIds(): string[] | null {
  try {
    const stored = localStorage.getItem(OPEN_TABS_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
}

function saveOpenTabIds(ids: string[]) {
  try {
    localStorage.setItem(OPEN_TABS_KEY, JSON.stringify(ids));
  } catch { /* ignore quota errors */ }
}

function reducer(state: ProjectsState, action: Action): ProjectsState {
  switch (action.type) {
    case 'SET_PROJECTS': {
      const ids = new Set(action.projects.map((p) => p.id));
      const activeStillExists = state.activeProjectId && ids.has(state.activeProjectId);
      // On initial load, restore tabs from localStorage; fall back to all projects
      let openTabIds: string[];
      if (state.openTabIds.length > 0) {
        openTabIds = state.openTabIds.filter((id) => ids.has(id));
      } else {
        const saved = loadOpenTabIds();
        openTabIds = saved
          ? saved.filter((id) => ids.has(id))
          : action.projects.map((p) => p.id);
      }
      saveOpenTabIds(openTabIds);
      return {
        ...state,
        projects: action.projects,
        openTabIds,
        activeProjectId: activeStillExists
          ? state.activeProjectId
          : openTabIds[0] ?? null,
      };
    }
    case 'SET_ACTIVE':
      return { ...state, activeProjectId: action.id };
    case 'ADD_PROJECT': {
      const newOpen = [...state.openTabIds, action.project.id];
      saveOpenTabIds(newOpen);
      return {
        ...state,
        projects: [...state.projects, action.project],
        openTabIds: newOpen,
        activeProjectId: action.project.id,
      };
    }
    case 'UPDATE_PROJECT':
      return {
        ...state,
        projects: state.projects.map((p) =>
          p.id === action.project.id ? action.project : p
        ),
      };
    case 'REMOVE_PROJECT': {
      const remaining = state.projects.filter((p) => p.id !== action.id);
      const openRemaining = state.openTabIds.filter((tid) => tid !== action.id);
      saveOpenTabIds(openRemaining);
      return {
        ...state,
        projects: remaining,
        openTabIds: openRemaining,
        activeProjectId:
          state.activeProjectId === action.id
            ? openRemaining[0] ?? null
            : state.activeProjectId,
      };
    }
    case 'OPEN_TAB': {
      if (state.openTabIds.includes(action.id)) {
        return { ...state, activeProjectId: action.id };
      }
      const newOpen = [...state.openTabIds, action.id];
      saveOpenTabIds(newOpen);
      return {
        ...state,
        openTabIds: newOpen,
        activeProjectId: action.id,
      };
    }
    case 'CLOSE_TAB': {
      const openRemaining = state.openTabIds.filter((tid) => tid !== action.id);
      saveOpenTabIds(openRemaining);
      return {
        ...state,
        openTabIds: openRemaining,
        activeProjectId:
          state.activeProjectId === action.id
            ? openRemaining[0] ?? null
            : state.activeProjectId,
      };
    }
  }
}

const ProjectsContext = createContext<ProjectsState>({
  projects: [],
  openTabIds: [],
  activeProjectId: null,
});

const DispatchContext = createContext<Dispatch<Action>>(() => {});

export function ProjectsProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, {
    projects: [],
    openTabIds: [],
    activeProjectId: null,
  });

  return (
    <ProjectsContext.Provider value={state}>
      <DispatchContext.Provider value={dispatch}>
        {children}
      </DispatchContext.Provider>
    </ProjectsContext.Provider>
  );
}

export function useProjects() {
  return useContext(ProjectsContext);
}

export function useDispatch() {
  return useContext(DispatchContext);
}
