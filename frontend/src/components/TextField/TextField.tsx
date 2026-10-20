import { type InputHTMLAttributes, useId } from 'react';

import { describedBy } from '../Field/describedBy';
import { Field } from '../Field/Field';
import control from '../Field/control.module.css';

export interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label: string;
  helper?: string | undefined;
  error?: string | undefined;
  size?: 'md' | 'lg';
}

export function TextField({
  label,
  helper,
  error,
  size = 'md',
  id,
  className,
  ...rest
}: TextFieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return (
    <Field id={inputId} label={label} helper={helper} error={error}>
      <input
        id={inputId}
        className={[control.control, size === 'lg' ? control.large : '', className]
          .filter(Boolean)
          .join(' ')}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(inputId, helper, error)}
        {...rest}
      />
    </Field>
  );
}
