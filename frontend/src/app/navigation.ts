import {
  FolderClock,
  Home,
  Layers,
  type LucideIcon,
  ScanText,
  Settings,
  SwatchBook,
} from 'lucide-react';

export interface NavItem {
  path: string;
  label: string;
  title: string;
  icon: LucideIcon;
  /** Two-key shortcut from DESIGN.md §7, e.g. "G H". */
  shortcut: string;
}

/** Primary navigation, in DESIGN.md §5.3 order. */
export const NAV_ITEMS: readonly NavItem[] = [
  { path: '/', label: 'Home', title: 'Home', icon: Home, shortcut: 'G H' },
  { path: '/editor', label: 'Editor', title: 'Editor', icon: ScanText, shortcut: 'G E' },
  {
    path: '/profiles',
    label: 'Profiles',
    title: 'Style Profiles',
    icon: SwatchBook,
    shortcut: 'G P',
  },
  { path: '/batch', label: 'Batch', title: 'Batch', icon: Layers, shortcut: 'G B' },
  { path: '/history', label: 'History', title: 'History', icon: FolderClock, shortcut: 'G Y' },
  { path: '/settings', label: 'Settings', title: 'Settings', icon: Settings, shortcut: 'G S' },
];

/** Second key of each "G X" shortcut → path, for useGoToShortcuts. */
export const GO_TO_TARGETS: Record<string, string> = Object.fromEntries(
  NAV_ITEMS.map((item) => [item.shortcut.split(' ')[1]?.toLowerCase() ?? '', item.path]),
);

export interface RouteHandle {
  title: string;
  /** Content fills the area without padding or max width (the Editor). */
  fullBleed?: boolean;
}
