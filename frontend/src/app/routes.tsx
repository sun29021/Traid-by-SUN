import type { ReactNode } from 'react';
import type { RouteObject } from 'react-router-dom';

import { ProfileDetailPage } from '@/features/profiles/ProfileDetailPage';
import { ProfilesPage } from '@/features/profiles/ProfilesPage';
import { WelcomeGate } from '@/features/welcome/WelcomeGate';
import { WelcomePage } from '@/features/welcome/WelcomePage';

import { AppShell } from './AppShell';
import { NAV_ITEMS, type RouteHandle } from './navigation';
import { NotFoundPage } from './NotFoundPage';
import { PlannedPage } from './PlannedPage';
import { RouteErrorPage } from './RouteErrorPage';

/** Sections that are built; the rest show a "planned" placeholder. */
const BUILT: Record<string, ReactNode> = {
  '/profiles': <ProfilesPage />,
};

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
  const profileHandle: RouteHandle = { title: 'Style Profiles' };
  return [
    ...NAV_ITEMS.map((item): RouteObject => {
      const planned = PLANNED[item.path];
      const handle: RouteHandle = { title: item.title };
      return {
        path: item.path,
        handle,
        element: BUILT[item.path] ?? (
          <PlannedPage
            icon={item.icon}
            title={item.title}
            description={planned?.description ?? ''}
            phase={planned?.phase ?? ''}
          />
        ),
      };
    }),
    { path: '/profiles/:profileId', handle: profileHandle, element: <ProfileDetailPage /> },
    { path: '/profiles/:profileId/:tab', handle: profileHandle, element: <ProfileDetailPage /> },
    {
      path: '*',
      handle: { title: 'Not found' } satisfies RouteHandle,
      element: <NotFoundPage />,
    },
  ];
}
