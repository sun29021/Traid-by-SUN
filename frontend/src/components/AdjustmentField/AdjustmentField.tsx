import { RotateCcw } from 'lucide-react';
import { useId } from 'react';

import styles from './AdjustmentField.module.css';

export interface AdjustmentFieldProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step: number;
  defaultValue: number;
  unit?: string;
  disabled?: boolean;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function decimals(step: number): number {
  const text = String(step);
  return text.includes('.') ? (text.split('.')[1]?.length ?? 0) : 0;
}

/**
 * Number + slider for editor adjustments (DESIGN.md §6.2): type a value, drag, or
 * double-click the slider to reset. A dot and a reset button show non-default values.
 */
export function AdjustmentField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  defaultValue,
  unit,
  disabled = false,
}: AdjustmentFieldProps) {
  const id = useId();
  const modified = value !== defaultValue;
  const display = value.toFixed(decimals(step));
  const reset = () => onChange(defaultValue);

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <label htmlFor={`${id}-number`} className={styles.label}>
          {modified ? <span className={styles.dot} aria-hidden /> : null}
          {label}
          {modified ? <span className="visually-hidden"> (changed)</span> : null}
        </label>
        <span className={styles.valueGroup}>
          <input
            id={`${id}-number`}
            type="number"
            className={styles.number}
            value={display}
            min={min}
            max={max}
            step={step}
            disabled={disabled}
            onChange={(event) => {
              const next = event.target.valueAsNumber;
              if (!Number.isNaN(next)) onChange(clamp(next, min, max));
            }}
          />
          {unit ? <span className={styles.unit}>{unit}</span> : null}
          <button
            type="button"
            className={styles.reset}
            onClick={reset}
            disabled={disabled || !modified}
            aria-label={`Reset ${label}`}
            title={`Reset ${label}`}
          >
            <RotateCcw aria-hidden />
          </button>
        </span>
      </div>
      <input
        type="range"
        className={styles.range}
        aria-label={label}
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(event) => onChange(event.target.valueAsNumber)}
        onDoubleClick={reset}
      />
    </div>
  );
}
