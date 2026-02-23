import { memo } from 'react';
import type { Project } from '../types';
import UploadStep from './UploadStep';
import SwatchGrid from './SwatchGrid';
import GenerateStep from './GenerateStep';
import ResultsGrid from './ResultsGrid';

interface Props {
  project: Project;
  apiKey: string;
}

export default memo(function ProjectTab({ project, apiKey }: Props) {
  return (
    <div className="project-columns">
      <div>
        <UploadStep project={project} apiKey={apiKey} />
        <SwatchGrid project={project} />
      </div>
      <div>
        <GenerateStep project={project} apiKey={apiKey} />
        <ResultsGrid project={project} />
      </div>
    </div>
  );
});
