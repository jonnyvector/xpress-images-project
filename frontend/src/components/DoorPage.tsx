// One door's workspace at /doors/:id. Only the open door is mounted, so doors
// you aren't looking at no longer poll the server in the background.
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';
import { useDispatch, useProjects } from '../context/ProjectsContext';
import { useApiKey } from '../hooks/useApiKey';
import * as api from '../api';
import { ApiError } from '../api';
import { showError } from '../notify';
import ProjectTab from './ProjectTab';

export default function DoorPage() {
  const { id = '' } = useParams();
  const { projects } = useProjects();
  const dispatch = useDispatch();
  const [apiKey] = useApiKey();
  const [failure, setFailure] = useState<{ id: string; missing: boolean } | null>(null);
  const project = projects.find((p) => p.id === id);

  useEffect(() => {
    let current = true;
    // Always fetch this door directly: the list may be minutes old (a running
    // generation picks its progress back up) or may have failed to load.
    api
      .getProject(id)
      .then((p) => {
        if (!current) return;
        dispatch({ type: 'UPDATE_PROJECT', project: p });
        dispatch({ type: 'VISIT', id });
      })
      .catch((err) => {
        if (!current) return;
        const missing = err instanceof ApiError && err.status === 404;
        setFailure({ id, missing });
        if (!missing) showError("Couldn't load this door", err);
      });
    return () => {
      current = false;
    };
  }, [id, dispatch]);

  if (!project) {
    if (failure?.id === id) {
      return (
        <div className="status-info">
          {failure.missing ? 'This door doesn\u2019t exist.' : 'Couldn\u2019t load this door.'}{' '}
          <Link to="/library">Back to the library</Link>
        </div>
      );
    }
    return <div className="status-info">Loading door…</div>;
  }
  // key: remount per door so per-door form state never leaks between doors.
  return <ProjectTab key={project.id} project={project} apiKey={apiKey} />;
}
