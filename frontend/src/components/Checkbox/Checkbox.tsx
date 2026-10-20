import { type InputHTMLAttributes, type ReactNode, useId } from 'react';

import styles from './Checkbox.module.css';

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: ReactNode;
  /** `switch` renders a toggle (DESIGN.md §6.2) with role="switch". */
  variant?: 'checkbox' | 'switch';
}

export function Checkbox({ label, variant = 'checkbox', id, className, ...rest }: CheckboxProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return (
    <label
      htmlFor={inputId}
      className={[styles.root, rest.disabled ? styles.disabled : '', className]
        .filter(Boolean)
        .join(' ')}
    >
      <input
        id={inputId}
        type="checkbox"
        role={variant === 'switch' ? 'switch' : undefined}
        className={variant === 'switch' ? styles.switch : styles.checkbox}
        {...rest}
      />
      <span>{label}</span>
    </label>
  );
}

export function Toggle(props: Omit<CheckboxProps, 'variant'>) {
  return <Checkbox {...props} variant="switch" />;
}
