/** Central TanStack Query keys so invalidation never misses a spelling. */
export const queryKeys = {
  health: ['health'] as const,
  systemStatus: ['system', 'status'] as const,
  welcome: ['system', 'welcome'] as const,
  activeTasks: ['tasks', 'active'] as const,
  task: (id: string) => ['tasks', id] as const,
};
