import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';

import { Badge, Banner, Button, Checkbox, type Tone } from '@/components';
import { ApiError } from '@/lib/api/client';
import { queryKeys } from '@/lib/api/queryKeys';
import { acceptWelcome, getHealth, getSystemStatus } from '@/lib/api/system';

import styles from './Welcome.module.css';
import { safeNextPath, useWelcome } from './useWelcome';

interface CheckRow {
  label: string;
  tone: Tone;
  status: string;
}

function useEngineChecks(): CheckRow[] {
  const health = useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => getHealth(signal),
    retry: false,
  });
  const status = useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: ({ signal }) => getSystemStatus(signal),
    retry: false,
  });

  const row = (label: string, tone: Tone, text: string): CheckRow => ({
    label,
    tone,
    status: text,
  });
  const checking = (label: string) => row(label, 'neutral', 'Checking…');

  const engine = health.isPending
    ? checking('Traid engine')
    : health.isError
      ? row('Traid engine', 'danger', 'Not responding')
      : row('Traid engine', 'success', `Running · v${health.data.version}`);

  const data = status.data;
  if (status.isPending || !data) {
    const unavailable = status.isError ? 'Not available' : null;
    return [
      engine,
      ...['Database', 'Background worker', 'AI models'].map((label) =>
        unavailable ? row(label, 'danger', unavailable) : checking(label),
      ),
    ];
  }
  return [
    engine,
    data.schema_revision
      ? row('Database', 'success', 'Ready')
      : row('Database', 'danger', 'Not available'),
    data.worker.running
      ? row('Background worker', 'success', 'Running')
      : row('Background worker', 'warning', 'Not running'),
    data.engine.ready
      ? row('AI models', 'success', `Ready · ${data.engine.device ?? 'CPU'}`)
      : row('AI models', 'info', 'Not installed yet'),
  ];
}

/** First-run screen: engine check + Acceptable Use (DESIGN.md §11.1, PRD §10 rule 6). */
export function WelcomePage() {
  const [params] = useSearchParams();
  const next = safeNextPath(params.get('next'));
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const welcome = useWelcome();
  const checks = useEngineChecks();
  const [agreed, setAgreed] = useState(false);

  useEffect(() => {
    document.title = 'Welcome — Traid';
  }, []);

  const accept = useMutation({
    mutationFn: acceptWelcome,
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.welcome, data);
      navigate(next, { replace: true });
    },
  });

  if (welcome.data?.aup_accepted) return <Navigate to={next} replace />;

  return (
    <div className={styles.page}>
      <main className={styles.column}>
        <header className={styles.brand}>
          <h1 className={styles.wordmark}>Traid</h1>
          <p className={styles.byline}>by Xavier Sun</p>
        </header>

        <section className={styles.section} aria-labelledby="engine-check">
          <h2 id="engine-check" className={styles.sectionTitle}>
            Engine check
          </h2>
          <ul className={styles.checks}>
            {checks.map((check) => (
              <li key={check.label} className={styles.check}>
                <span>{check.label}</span>
                <Badge tone={check.tone} label={check.status} />
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.section} aria-labelledby="acceptable-use">
          <h2 id="acceptable-use" className={styles.sectionTitle}>
            Acceptable use
          </h2>
          <p className={styles.text}>
            Traid edits text in images so that it looks like the original print. Only use it on
            images and documents you own or are authorized to produce and edit. Never use it to
            alter identity documents, money, financial instruments, official certificates or other
            people&apos;s documents.
          </p>
          <Checkbox
            label="I will only edit images I own or am authorized to edit."
            checked={agreed}
            onChange={(event) => setAgreed(event.target.checked)}
          />
        </section>

        {accept.isError ? (
          <Banner
            tone="danger"
            title="Could not save your acknowledgement."
            code={accept.error instanceof ApiError ? accept.error.code : undefined}
          >
            {accept.error.message}
          </Banner>
        ) : null}

        <Button
          variant="primary"
          size="lg"
          disabled={!agreed}
          loading={accept.isPending}
          onClick={() => accept.mutate()}
        >
          Start using Traid
        </Button>

        <footer className={styles.footer}>Traid · Designed &amp; developed by Xavier Sun</footer>
      </main>
    </div>
  );
}
