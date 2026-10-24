import { Navigate, Route, Routes } from 'react-router';
import { ProjectsProvider } from './context/ProjectsContext';
import AppShell from './components/AppShell';
import DoorLibrary from './components/DoorLibrary';
import ReviewQueue from './components/ReviewQueue';
import CoveragePage from './components/CoveragePage';
import DoorPage from './components/DoorPage';

export default function App() {
  return (
    <ProjectsProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/library" replace />} />
          <Route path="library" element={<DoorLibrary />} />
          <Route path="review" element={<ReviewQueue />} />
          <Route path="coverage" element={<CoveragePage />} />
          <Route path="doors/:id" element={<DoorPage />} />
          <Route path="*" element={<Navigate to="/library" replace />} />
        </Route>
      </Routes>
    </ProjectsProvider>
  );
}
