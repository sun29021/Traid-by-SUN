import type { RouteObject } from 'react-router-dom';

import { WelcomeGate } from '@/features/welcome/WelcomeGate';
import { WelcomePage } from '@/features/welcome/WelcomePage';

import { AppShell } from './AppShell';
import { NAV_ITEMS, type RouteHandle } from './navigation';
import { NotFoundPage } from './NotFoundPage';
import { PlannedPage } from './PlannedPage';
import { RouteErrorPage } from './RouteErrorPage';

const PLANNED: Record<string, { description: string; phase: string }> = {
  '/': {
    description:
      'Drop a target image here to start an edit, and see recent jobs and profile readiness.',
    phase: 'Phase 10',
  },
  '/editor': {
    description: 'Detect the token, type the new value, generate, review and export.',
    phase: 'Phase 10',
  },
  '/profiles': {
    description: 'Train Style Profiles from real reference images and review their glyphs.',
    phase: 'Phase 6',
  },
  '/batch': {
    description: 'Apply a list of token values to one template image.',
    phase: 'Phase 12',
  },
  '/history': {
    description: 'Find, re-open and re-export past edit jobs.',
    phase: 'Phase 13',
  },
  '/settings': {
    description: 'Account, engine status, export defaults, storage, backup, audit log and About.',
    phase: 'Phase 13',
  },
};

export const routes: RouteObject[] = [
  {
    path: '/welcome',
    handle: { title: 'Welcome' } satisfies RouteHandle,
    element: <WelcomePage />,
    errorElement: <RouteErrorPage />,
  },
  {
    element: <WelcomeGate />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <AppShell />,
        errorElement: <RouteErrorPage />,
        children: appRoutes(),
      },
    ],
  },
];

function appRoutes(): RouteObject[] {
  return [
    ...NAV_ITEMS.map((item): RouteObject => {
      const planned = PLANNED[item.path];
      const handle: RouteHandle = { title: item.title };
      return {
        path: item.path,
        handle,
        element: (
          <PlannedPage
            icon={item.icon}
            title={item.title}
            description={planned?.description ?? ''}
            phase={planned?.phase ?? ''}
          />
        ),
      };
    }),
    {
      path: '*',
      handle: { title: 'Not found' } satisfies RouteHandle,
      element: <NotFoundPage />,
    },
  ];
}
