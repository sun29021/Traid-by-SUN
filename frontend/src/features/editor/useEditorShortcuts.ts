import { useEffect, useRef } from 'react';

import type { EditorAction } from './editorStore';

export interface EditorShortcutHandlers {
  dispatch: (action: EditorAction) => void;
  generate: () => void;
  accept: () => void;
  reject: () => void;
  exportFile: () => void;
  focusToken: () => void;
  toggleRegionsPanel: () => void;
  toggleInspector: () => void;
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

/**
 * Editor keyboard shortcuts (DESIGN.md §10.1). Single-letter keys are ignored while
 * typing; Ctrl+Enter works from the token field. `G` stays with "go to" navigation.
 */
export function useEditorShortcuts(handlers: EditorShortcutHandlers) {
  const ref = useRef(handlers);
  useEffect(() => {
    ref.current = handlers;
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const h = ref.current;
      const ctrl = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
      if (ctrl && key === 'enter') {
        event.preventDefault();
        h.generate();
        return;
      }
      if (ctrl && event.shiftKey && key === 'a') {
        event.preventDefault();
        h.accept();
        return;
      }
      if (ctrl && event.shiftKey && key === 'r') {
        event.preventDefault();
        h.reject();
        return;
      }
      if (ctrl && !event.shiftKey && key === 'e') {
        event.preventDefault();
        h.exportFile();
        return;
      }
      if (isTyping(event.target)) return;
      if (ctrl && key === 'z') {
        event.preventDefault();
        h.dispatch({ type: event.shiftKey ? 'redo' : 'undo' });
        return;
      }
      if (ctrl || event.altKey) return;
      if (event.key === '\\') h.dispatch({ type: 'toggleView' });
      else if (key === 's') h.dispatch({ type: 'toggleSplit' });
      else if (key === 'm') h.dispatch({ type: 'toggleMask' });
      else if (key === 't') {
        event.preventDefault();
        h.focusToken();
      } else if (event.key === '[') h.toggleRegionsPanel();
      else if (event.key === ']') h.toggleInspector();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
}
