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
const queryClient = createQueryClient({
  onAupRequired: () => {
    const { pathname, search } = router.state.location;
    if (pathname !== '/welcome') {
      void router.navigate(`/welcome?next=${encodeURIComponent(pathname + search)}`, {
        replace: true,
      });
    }
  },
});

createRoot(container).render(
  <StrictMode>
    <Providers client={queryClient}>
      <RouterProvider router={router} />
    </Providers>
  </StrictMode>,
);
