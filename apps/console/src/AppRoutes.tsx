import { Navigate, Route, Routes } from 'react-router-dom';
import { RequireAuth } from './shell/ConsoleShell';
import { ConsoleShell } from './shell/ConsoleShell';
import { LoginPage } from './views/LoginPage';
import { ProvidersPage } from './views/ProvidersPage';
import { SchemaPage } from './views/SchemaPage';
import { HealthPage } from './views/HealthPage';
import { AuditPage } from './views/AuditPage';

export function AppRoutes(): JSX.Element {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<ConsoleShell />}>
          <Route path="/providers" element={<ProvidersPage />} />
          <Route path="/schema" element={<SchemaPage />} />
          <Route path="/health" element={<HealthPage />} />
          <Route path="/audit" element={<AuditPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/providers" replace />} />
    </Routes>
  );
}
