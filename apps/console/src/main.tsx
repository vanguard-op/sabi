import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { AppRoutes } from './AppRoutes';
import { AuthProvider } from './auth/AuthProvider';
import { ConsoleDataProvider } from './data/ConsoleDataProvider';
import { ThemeProvider } from './theme/ThemeProvider';
import './styles.css';

const container = document.getElementById('root');
if (!container) throw new Error('Root element not found');

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <ConsoleDataProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </ConsoleDataProvider>
      </AuthProvider>
    </ThemeProvider>
  </StrictMode>,
);
