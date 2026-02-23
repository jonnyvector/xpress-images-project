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

function reducer(state: ProjectsState, action: Action): ProjectsState {
  switch (action.type) {
    case 'SET_PROJECTS': {
      const ids = new Set(action.projects.map((p) => p.id));
      const activeStillExists = state.activeProjectId && ids.has(state.activeProjectId);
      // On initial load, open tabs for all projects
      const openTabIds = state.openTabIds.length > 0
        ? state.openTabIds.filter((id) => ids.has(id))
        : action.projects.map((p) => p.id);
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
    case 'ADD_PROJECT':
      return {
        ...state,
        projects: [...state.projects, action.project],
        openTabIds: [...state.openTabIds, action.project.id],
        activeProjectId: action.project.id,
      };
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
      return {
        ...state,
        openTabIds: [...state.openTabIds, action.id],
        activeProjectId: action.id,
      };
    }
    case 'CLOSE_TAB': {
      const openRemaining = state.openTabIds.filter((tid) => tid !== action.id);
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
