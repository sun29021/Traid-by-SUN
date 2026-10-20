/** Plain-language names for audit actions (DATABASE.md §3.11). */
const ACTION_LABELS: Record<string, string> = {
  'system.aup_accepted': 'Acceptable use accepted',
  'profile.created': 'Profile created',
  'profile.archived': 'Profile archived',
  'profile.deleted': 'Profile deleted',
  'job.accepted': 'Edit accepted',
  'job.rejected': 'Edit rejected',
  'job.exported': 'Edit exported',
  'job.deleted': 'Edit deleted',
  'batch.exported': 'Batch exported',
  'settings.updated': 'Settings changed',
  'backup.created': 'Backup created',
};

export function auditLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}
