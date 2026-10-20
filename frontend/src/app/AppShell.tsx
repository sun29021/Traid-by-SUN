import { useQuery } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { useEffect } from 'react';
import { NavLink, Outlet, useMatches, useNavigate } from 'react-router-dom';

import { Banner, Button } from '@/components';
import { queryKeys } from '@/lib/api/queryKeys';
import { getHealth } from '@/lib/api/system';
import { listTasks } from '@/lib/api/tasks';
import { useGoToShortcuts } from '@/lib/hooks/useGoToShortcuts';

import styles from './AppShell.module.css';
import { GO_TO_TARGETS, NAV_ITEMS, type RouteHandle } from './navigation';

const HEALTH_POLL_MS = 15_000;
const TASKS_POLL_ACTIVE_MS = 2_000;
const TASKS_POLL_IDLE_MS = 10_000;

function useRouteHandle(): RouteHandle {
  const matches = useMatches();
  const handle = matches.at(-1)?.handle as RouteHandle | undefined;
  return handle ?? { title: 'Traid' };
}

function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => getHealth(signal),
    refetchInterval: HEALTH_POLL_MS,
    retry: false,
  });
}

function EngineStatus() {
  const health = useHealth();
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

/** Full-width warning when the local server stops answering (DESIGN.md §9.1). */
function EngineOfflineBanner() {
  const health = useHealth();
  if (!health.isError) return null;
  return (
    <div className={styles.offline}>
      <Banner
        tone="danger"
        title="Traid engine is not responding."
        action={
          <Button onClick={() => void health.refetch()} loading={health.isFetching}>
            Retry
          </Button>
        }
      >
        Start it with scripts\dev.ps1 or scripts\start.ps1, then retry.
      </Banner>
    </div>
  );
}

/** Running background work, shown in the top bar; hidden when idle. */
function TasksChip() {
  const tasks = useQuery({
    queryKey: queryKeys.activeTasks,
    queryFn: ({ signal }) => listTasks({}, signal),
    refetchInterval: (query) =>
      (query.state.data?.items.length ?? 0) > 0 ? TASKS_POLL_ACTIVE_MS : TASKS_POLL_IDLE_MS,
  });
  const count = tasks.data?.items.length ?? 0;
  if (count === 0) return null;
  return (
    <span className={styles.tasksChip} role="status">
      <Loader2 className={styles.spin} aria-hidden />
      {count === 1 ? '1 task running' : `${count} tasks running`}
    </span>
  );
}

/** App shell: nav rail + top bar + page content (DESIGN.md §5.3). */
export function AppShell() {
  const { title, fullBleed = false } = useRouteHandle();
  const navigate = useNavigate();
  useGoToShortcuts(GO_TO_TARGETS, navigate);

  useEffect(() => {
    document.title = title === 'Traid' ? 'Traid' : `${title} — Traid`;
  }, [title]);

  return (
    <div className={styles.shell}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <nav className={styles.rail} aria-label="Primary">
        <div className={styles.wordmark}>
          <span aria-hidden>T</span>
          <span className="visually-hidden">Traid</span>
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
        <EngineOfflineBanner />
        <header className={styles.topBar}>
          <h1 className={styles.pageTitle}>{title}</h1>
          <TasksChip />
        </header>
        <main id="main" className={fullBleed ? styles.fullBleed : styles.content} tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
