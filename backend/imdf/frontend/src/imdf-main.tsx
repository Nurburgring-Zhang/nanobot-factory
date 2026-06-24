import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './imdf-app';
import './styles/index.css';

const app = import.meta.env.DEV && import.meta.env.VITE_T8_STRICT_MODE !== '1'
  ? <App />
  : (
    <StrictMode>
      <App />
    </StrictMode>
  );

const rootEl = document.getElementById('root');
if (rootEl) {
  createRoot(rootEl).render(app);
}

export {};
