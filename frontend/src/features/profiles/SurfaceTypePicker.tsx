import { useId } from 'react';

import type { SurfaceType } from '@/lib/api/types';

import { SURFACE_TYPES } from './profileMeta';
import styles from './SurfaceTypePicker.module.css';

interface SurfaceTypePickerProps {
  value: SurfaceType | null;
  onChange: (value: SurfaceType) => void;
  error?: string | undefined;
}

/** Four-option segmented control with a hint per option (DESIGN.md §11.3). */
export function SurfaceTypePicker({ value, onChange, error }: SurfaceTypePickerProps) {
  const name = useId();
  return (
    <fieldset className={styles.fieldset} aria-invalid={error ? true : undefined}>
      <legend className={styles.legend}>Surface type</legend>
      <div className={styles.options}>
        {SURFACE_TYPES.map((option) => (
          <label
            key={option.value}
            className={[styles.option, value === option.value ? styles.selected : ''].join(' ')}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="visually-hidden"
            />
            <span className={styles.label}>{option.label}</span>
            <span className={styles.hint}>{option.hint}</span>
          </label>
        ))}
      </div>
      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}
