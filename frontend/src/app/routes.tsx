import type { ReactNode } from 'react';
import type { RouteObject } from 'react-router-dom';

import { BatchPage } from '@/features/batch/BatchPage';
import { EditorPage } from '@/features/editor/EditorPage';
import { HistoryPage } from '@/features/history/HistoryPage';
import { HomePage } from '@/features/home/HomePage';
import { ProfileDetailPage } from '@/features/profiles/ProfileDetailPage';
import { ProfilesPage } from '@/features/profiles/ProfilesPage';
import { SettingsPage } from '@/features/settings/SettingsPage';
import { WelcomeGate } from '@/features/welcome/WelcomeGate';
import { WelcomePage } from '@/features/welcome/WelcomePage';

import { AppShell } from './AppShell';
import { NAV_ITEMS, type RouteHandle } from './navigation';
import { NotFoundPage } from './NotFoundPage';
import { PlannedPage } from './PlannedPage';
import { RouteErrorPage } from './RouteErrorPage';

/** Sections that are built; the rest show a "planned" placeholder. */
const BUILT: Record<string, ReactNode> = {
  '/': <HomePage />,
  '/editor': <EditorPage />,
  '/profiles': <ProfilesPage />,
  '/batch': <BatchPage />,
  '/history': <HistoryPage />,
  '/settings': <SettingsPage />,
};

/** Pages that use the whole content area without padding (DESIGN.md §11.5). */
const FULL_BLEED = new Set(['/editor']);

const PLANNED: Record<string, { description: string; phase: string }> = {};

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
      const handle: RouteHandle = { title: item.title, fullBleed: FULL_BLEED.has(item.path) };
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
    {
      path: '/editor/:jobId',
      handle: { title: 'Editor', fullBleed: true } satisfies RouteHandle,
      element: <EditorPage />,
    },
    {
      path: '/history/:jobId',
      handle: { title: 'History' } satisfies RouteHandle,
      element: <HistoryPage />,
    },
    {
      path: '/settings/:tab',
      handle: { title: 'Settings' } satisfies RouteHandle,
      element: <SettingsPage />,
    },
    {
      path: '/batch/:batchId',
      handle: { title: 'Batch' } satisfies RouteHandle,
      element: <BatchPage />,
    },
    { path: '/profiles/:profileId', handle: profileHandle, element: <ProfileDetailPage /> },
    { path: '/profiles/:profileId/:tab', handle: profileHandle, element: <ProfileDetailPage /> },
    {
      path: '*',
      handle: { title: 'Not found' } satisfies RouteHandle,
      element: <NotFoundPage />,
    },
  ];
}
