import './styles/fonts.css';
import './styles/tokens.css';
import './styles/base.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

import { Providers } from './app/providers';
import { createQueryClient } from './app/queryClient';
import { routes } from './app/routes';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root element #root is missing from index.html');
}

const router = createBrowserRouter(routes);

createRoot(container).render(
  <StrictMode>
    <Providers client={createQueryClient()}>
      <RouterProvider router={router} />
    </Providers>
  </StrictMode>,
);
