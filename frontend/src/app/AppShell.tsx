import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { NavLink, Outlet, useMatches } from 'react-router-dom';

import { getHealth } from '@/lib/api/system';

import styles from './AppShell.module.css';
import { NAV_ITEMS, type RouteHandle } from './navigation';

const HEALTH_POLL_MS = 15_000;

function useRouteTitle(): string {
  const matches = useMatches();
  const handle = matches.at(-1)?.handle as RouteHandle | undefined;
  return handle?.title ?? 'Traid';
}

function EngineStatus() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => getHealth(signal),
    refetchInterval: HEALTH_POLL_MS,
    retry: false,
  });
  const state = health.isPending ? 'checking' : health.isError ? 'offline' : 'online';
  const label = {
    checking: 'Checking engine…',
    offline: 'Engine offline',
    online: `Engine online · v${health.data?.version ?? ''}`,
  }[state];

  return (
    <div className={styles.engine} data-state={state} title={label}>
      <span className={styles.engineDot} aria-hidden />
      <span className="visually-hidden">{label}</span>
    </div>
  );
}

/** App shell: nav rail + top bar + page content (DESIGN.md §5.3). */
export function AppShell() {
  const title = useRouteTitle();

  useEffect(() => {
    document.title = title === 'Traid' ? 'Traid' : `${title} — Traid`;
  }, [title]);

  return (
    <div className={styles.shell}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <nav className={styles.rail} aria-label="Primary">
        <div className={styles.wordmark} aria-label="Traid">
          T
        </div>
        <ul className={styles.navList}>
          {NAV_ITEMS.map(({ path, label, icon: Icon, shortcut }) => (
            <li key={path}>
              <NavLink
                to={path}
                end={path === '/'}
                className={({ isActive }) =>
                  [styles.navItem, isActive ? styles.navItemActive : ''].join(' ')
                }
                title={`${label}  ${shortcut}`}
              >
                <Icon className={styles.navIcon} aria-hidden />
                <span className={styles.navLabel}>{label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
        <div className={styles.railFooter}>
          <EngineStatus />
          <p className={styles.credit}>by Xavier Sun</p>
        </div>
      </nav>

      <div className={styles.main}>
        <header className={styles.topBar}>
          <h1 className={styles.pageTitle}>{title}</h1>
        </header>
        <main id="main" className={styles.content} tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
