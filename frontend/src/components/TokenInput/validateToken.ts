export interface TokenValidation {
  /** Unique characters (in order of appearance) that are not in the profile's charset. */
  invalidChars: string[];
  /** null when the profile has no pattern (or the pattern cannot be compiled in JS). */
  patternMatches: boolean | null;
}

/**
 * Client-side mirror of the server's token checks (API.md §3.6). The server stays the
 * authority; this only gives instant feedback while typing.
 */
export function validateToken(
  value: string,
  charset: string,
  pattern?: string | null,
): TokenValidation {
  const allowed = new Set(charset);
  const invalidChars = [...new Set([...value].filter((char) => !allowed.has(char)))];

  let patternMatches: boolean | null = null;
  if (pattern) {
    try {
      patternMatches = new RegExp(pattern).test(value);
    } catch {
      patternMatches = null;
    }
  }
  return { invalidChars, patternMatches };
}

export function describeChar(char: string): string {
  return char === ' ' ? 'space' : char;
}
