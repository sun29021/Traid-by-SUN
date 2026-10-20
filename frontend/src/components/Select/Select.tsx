import { type SelectHTMLAttributes, useId } from 'react';

import { describedBy } from '../Field/describedBy';
import { Field } from '../Field/Field';
import control from '../Field/control.module.css';
import styles from './Select.module.css';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children'> {
  label: string;
  options: readonly SelectOption[];
  helper?: string;
  error?: string;
}

/** Native select: keyboard search and accessibility come for free (DESIGN.md §6.2). */
export function Select({ label, options, helper, error, id, className, ...rest }: SelectProps) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  return (
    <Field id={selectId} label={label} helper={helper} error={error}>
      <select
        id={selectId}
        className={[control.control, styles.select, className].filter(Boolean).join(' ')}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(selectId, helper, error)}
        {...rest}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
    </Field>
  );
}
