import type { SystemStatus } from '@/lib/api/types';

type Device = NonNullable<SystemStatus['engine']['device']>;

const LABELS: Record<Device, string> = {
  cpu: 'CPU',
  directml: 'GPU (DirectML)',
  cuda: 'GPU (CUDA)',
};

/** Human-readable inference device, e.g. "GPU (DirectML)". */
export function deviceLabel(device: Device | null | undefined): string {
  return device ? LABELS[device] : 'CPU';
}
