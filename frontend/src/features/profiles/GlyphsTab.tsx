import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ScanSearch } from 'lucide-react';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { Banner, Button, EmptyState, Select, Skeleton, useToast } from '@/components';
import { ApiError } from '@/lib/api/client';
import { bulkUpdateGlyphs, type GlyphFilters, listAllGlyphs } from '@/lib/api/profiles';
import { queryKeys } from '@/lib/api/queryKeys';
import type { GlyphStatus, Profile } from '@/lib/api/types';

import { GlyphGrid } from './GlyphGrid';
import styles from './Glyphs.module.css';
import { displayChar } from './profileMeta';
import { useCoverage } from './useProfile';

const STATUS_FILTERS: { value: 'all' | GlyphStatus; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'auto', label: 'To review' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'rejected', label: 'Rejected' },
];

export function GlyphsTab({ profile }: { profile: Profile }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const char = params.get('char') ?? undefined;
  const status = (params.get('status') ?? 'all') as 'all' | GlyphStatus;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [relabelChar, setRelabelChar] = useState('');
  const coverage = useCoverage(profile.id);
  const readOnly = Boolean(profile.archived_at);

  const filters: GlyphFilters = { char, status: status === 'all' ? undefined : [status] };
  const glyphs = useQuery({
    queryKey: queryKeys.glyphs(profile.id, filters),
    queryFn: ({ signal }) => listAllGlyphs(profile.id, filters, signal),
  });

  const setFilter = (key: 'char' | 'status', value: string | undefined) => {
    const next = new URLSearchParams(params);
    if (value && value !== 'all') next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
    setSelected(new Set());
  };

  const review = useMutation({
    mutationFn: (body: {
      ids: string[];
      action: 'confirm' | 'reject' | 'relabel';
      char?: string;
    }) => bulkUpdateGlyphs(profile.id, body),
    onSuccess: (result, body) => {
      for (const key of [
        queryKeys.allGlyphs(profile.id),
        queryKeys.profile(profile.id),
        queryKeys.coverage(profile.id),
        queryKeys.profiles,
      ]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
      const verb = { confirm: 'confirmed', reject: 'rejected', relabel: 'relabelled' }[body.action];
      toast({
        message: `${result.updated} glyph${result.updated === 1 ? '' : 's'} ${verb}`,
        tone: 'success',
      });
      setSelected(new Set());
    },
    onError: (error) =>
      toast({
        message: error instanceof ApiError ? error.message : 'Review could not be saved',
        tone: 'danger',
      }),
  });

  const act = (action: 'confirm' | 'reject', ids: string[]) => {
    if (!readOnly && ids.length) review.mutate({ ids, action });
  };
  const relabel = (ids: string[], value: string) => {
    if (readOnly || !ids.length) return;
    if (value === ' ' || !profile.charset.includes(value)) {
      toast({ message: `“${value}” is not in this profile's character set`, tone: 'danger' });
      return;
    }
    review.mutate({ ids, action: 'relabel', char: value });
  };

  const chars = coverage.data ?? [];
  return (
    <div className={styles.layout}>
      <aside className={styles.filters} aria-label="Glyph filters">
        <div className={styles.filterGroup} role="group" aria-label="Status">
          {STATUS_FILTERS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={status === option.value}
              className={styles.filterButton}
              onClick={() => setFilter('status', option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className={styles.charList} role="group" aria-label="Character">
          <button
            type="button"
            aria-pressed={!char}
            className={styles.charButton}
            onClick={() => setFilter('char', undefined)}
          >
            <span>All characters</span>
          </button>
          {chars.map((item) => (
            <button
              key={item.char}
              type="button"
              aria-pressed={char === item.char}
              className={styles.charButton}
              onClick={() => setFilter('char', item.char)}
            >
              <span className={styles.charLabel}>{displayChar(item.char)}</span>
              <span className={styles.charCounts}>
                {item.confirmed}
                {item.auto ? <span className={styles.autoCount}> +{item.auto}</span> : null}
              </span>
            </button>
          ))}
        </div>
      </aside>

      <div className={styles.main}>
        <p className={styles.help}>
          Arrow keys move · Space selects · Enter confirms · Delete rejects · type a character to
          relabel · Ctrl+A selects all · Esc clears
        </p>
        {glyphs.isPending ? (
          <div className={styles.tiles} aria-label="Loading glyphs">
            {Array.from({ length: 12 }, (_, i) => (
              <Skeleton key={i} variant="block" width={72} height={88} />
            ))}
          </div>
        ) : glyphs.isError ? (
          <Banner
            tone="danger"
            title="Glyphs could not be loaded."
            action={<Button onClick={() => void glyphs.refetch()}>Retry</Button>}
          />
        ) : glyphs.data.length === 0 ? (
          <EmptyState
            icon={<ScanSearch />}
            title={char || status !== 'all' ? 'No glyphs match these filters' : 'No glyphs yet'}
            description={
              char || status !== 'all'
                ? 'Clear the filters to see every glyph.'
                : 'Upload reference images; their characters appear here for review.'
            }
          />
        ) : (
          <GlyphGrid
            glyphs={glyphs.data}
            selected={selected}
            focusedId={focusedId}
            onFocus={setFocusedId}
            onSelectionChange={setSelected}
            onConfirm={(ids) => act('confirm', ids)}
            onReject={(ids) => act('reject', ids)}
            onRelabel={relabel}
          />
        )}
      </div>

      {selected.size > 0 && !readOnly ? (
        <div className={styles.bulkBar} role="region" aria-label="Selected glyphs">
          <span>{selected.size} selected</span>
          <Button
            variant="primary"
            loading={review.isPending}
            onClick={() => act('confirm', [...selected])}
          >
            Confirm
          </Button>
          <Button variant="danger" onClick={() => act('reject', [...selected])}>
            Reject
          </Button>
          <div className={styles.relabel}>
            <Select
              label="Relabel as"
              value={relabelChar}
              onChange={(e) => setRelabelChar(e.target.value)}
              options={[
                { value: '', label: 'Choose…' },
                ...[...profile.charset]
                  .filter((c) => c !== ' ')
                  .map((c) => ({ value: c, label: c })),
              ]}
            />
            <Button disabled={!relabelChar} onClick={() => relabel([...selected], relabelChar)}>
              Apply
            </Button>
          </div>
          <Button variant="ghost" onClick={() => setSelected(new Set())}>
            Clear
          </Button>
        </div>
      ) : null}
    </div>
  );
}
