import { CircleCheck, CircleX } from 'lucide-react';
import { type InputHTMLAttributes, useId } from 'react';

import { describedBy } from '../Field/describedBy';
import { Field } from '../Field/Field';
import control from '../Field/control.module.css';
import styles from './TokenInput.module.css';
import { describeChar, validateToken } from './validateToken';

export const MAX_TOKEN_LENGTH = 64;

export interface TokenInputProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'value' | 'onChange' | 'size' | 'pattern'
> {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** The profile's character set; characters outside it are flagged. */
  charset: string;
  pattern?: string | null | undefined;
  helper?: string | undefined;
}

/** Mono token entry with live charset and pattern feedback (DESIGN.md §6.2). */
export function TokenInput({
  label,
  value,
  onChange,
  charset,
  pattern,
  helper,
  id,
  className,
  ...rest
}: TokenInputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const { invalidChars, patternMatches } = validateToken(value, charset, pattern);
  const error = invalidChars.length
    ? `Not in this profile's character set: ${invalidChars.map(describeChar).join(', ')}`
    : undefined;

  const patternChip =
    pattern && value && patternMatches !== null ? (
      <span
        className={[styles.chip, patternMatches ? styles.pass : styles.fail].join(' ')}
        aria-live="polite"
      >
        {patternMatches ? <CircleCheck aria-hidden /> : <CircleX aria-hidden />}
        {patternMatches ? 'Pattern matches' : 'Pattern does not match'}
      </span>
    ) : null;

  return (
    <Field id={inputId} label={label} helper={helper} error={error} labelAside={patternChip}>
      <div className={styles.wrap}>
        <input
          id={inputId}
          className={[control.control, control.large, styles.input, className]
            .filter(Boolean)
            .join(' ')}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          maxLength={MAX_TOKEN_LENGTH}
          spellCheck={false}
          autoComplete="off"
          autoCapitalize="off"
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(inputId, helper, error)}
          {...rest}
        />
        <span className={styles.count} aria-hidden>
          {value.length}/{MAX_TOKEN_LENGTH}
        </span>
      </div>
    </Field>
  );
}
