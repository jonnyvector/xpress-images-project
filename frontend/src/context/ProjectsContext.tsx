import { createContext, useContext, useReducer, type ReactNode, type Dispatch } from 'react';
import type { Project } from '../types';

interface ProjectsState {
  projects: Project[];
  activeProjectId: string | null;
}

type Action =
  | { type: 'SET_PROJECTS'; projects: Project[] }
  | { type: 'SET_ACTIVE'; id: string }
  | { type: 'ADD_PROJECT'; project: Project }
  | { type: 'UPDATE_PROJECT'; project: Project }
  | { type: 'REMOVE_PROJECT'; id: string };

function reducer(state: ProjectsState, action: Action): ProjectsState {
  switch (action.type) {
    case 'SET_PROJECTS': {
      const ids = new Set(action.projects.map((p) => p.id));
      const activeStillExists = state.activeProjectId && ids.has(state.activeProjectId);
      return {
        ...state,
        projects: action.projects,
        activeProjectId: activeStillExists
          ? state.activeProjectId
          : action.projects[0]?.id ?? null,
      };
    }
    case 'SET_ACTIVE':
      return { ...state, activeProjectId: action.id };
    case 'ADD_PROJECT':
      return {
        ...state,
        projects: [...state.projects, action.project],
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
      return {
        ...state,
        projects: remaining,
        activeProjectId:
          state.activeProjectId === action.id
            ? remaining[0]?.id ?? null
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
