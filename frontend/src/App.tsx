import { ProjectsProvider } from './context/ProjectsContext';
import Layout from './components/Layout';

export default function App() {
  return (
    <ProjectsProvider>
      <Layout />
    </ProjectsProvider>
  );
}
