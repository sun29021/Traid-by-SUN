/** Central TanStack Query keys so invalidation never misses a spelling. */
export const queryKeys = {
  health: ['health'] as const,
  systemStatus: ['system', 'status'] as const,
  welcome: ['system', 'welcome'] as const,
  activeTasks: ['tasks', 'active'] as const,
  task: (id: string) => ['tasks', id] as const,

  profiles: ['profiles'] as const,
  profileList: (archived: string) => ['profiles', 'list', archived] as const,
  profile: (id: string) => ['profiles', id] as const,
  coverage: (id: string) => ['profiles', id, 'coverage'] as const,
  learning: (id: string) => ['profiles', id, 'learning'] as const,
  references: (id: string) => ['profiles', id, 'references'] as const,
  glyphs: (id: string, filters: unknown) => ['profiles', id, 'glyphs', filters] as const,
  allGlyphs: (id: string) => ['profiles', id, 'glyphs'] as const,

  jobs: ['jobs'] as const,
  jobList: (filters: unknown) => ['jobs', 'list', filters] as const,
  job: (id: string) => ['jobs', id] as const,
  glyphVariants: (id: string, position: number) => ['jobs', id, 'variants', position] as const,
};
