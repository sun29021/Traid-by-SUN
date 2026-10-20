import { useEffect } from 'react';

const SEQUENCE_TIMEOUT_MS = 1000;

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

/**
 * Two-key "G then X" navigation shortcuts (DESIGN.md §7), e.g. G H → Home.
 * Ignored while typing in a field or when a modifier key is held.
 */
export function useGoToShortcuts(targets: Record<string, string>, go: (path: string) => void) {
  useEffect(() => {
    let armedAt = 0;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey || isTyping(event.target)) return;
      const key = event.key.toLowerCase();
      if (armedAt && Date.now() - armedAt < SEQUENCE_TIMEOUT_MS) {
        armedAt = 0;
        const path = targets[key];
        if (path) {
          event.preventDefault();
          go(path);
        }
        return;
      }
      armedAt = key === 'g' ? Date.now() : 0;
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [targets, go]);
}
