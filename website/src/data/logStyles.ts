/**
 * Log line styles for the simulated terminal.
 *
 * Aligned with juris CLI output patterns.
 */

// ---------------------------------------------------------------------------
// Style registry
// ---------------------------------------------------------------------------

export interface LogStyle {
  /** Tailwind CSS class(es) applied to the rendered line */
  className: string;
}

/** Named styles that output lines can reference. */
export const LOG_STYLES = {
  /** Success / completion (green) */
  success: { className: "text-[#4ade80]" },
  /** Failure / error (red) */
  failure: { className: "text-[#f87171]" },
  /** Info / progress (accent amber) */
  info: { className: "text-accent" },
  /** Agent activity (blue) */
  agent: { className: "text-[#60a5fa]" },
  /** Result data (teal) */
  result: { className: "text-[#2dd4bf]" },
  /** Stat lines */
  stat: { className: "text-text-secondary" },
  /** Default dim output */
  dim: { className: "text-text-dim" },
  /** Zag reference (purple) */
  zag: { className: "text-zag" },
} as const;

export type LogStyleName = keyof typeof LOG_STYLES;

// ---------------------------------------------------------------------------
// Terminal line types (shared between demo data and animation hook)
// ---------------------------------------------------------------------------

/** A single output line: plain string (defaults to "dim") or annotated. */
export type OutputLine = string | { text: string; style: LogStyleName };

export type TerminalLine =
  | { type: "command"; text: string; typingSpeed?: number }
  | { type: "output"; lines: OutputLine[]; delay?: number }
  | { type: "comment"; text: string }
  | { type: "pause"; duration: number };

export type TerminalTab = {
  label: string;
  sequence: TerminalLine[];
};

/** Produced by useTerminalAnimation, consumed by TerminalLine renderer. */
export type RenderedLine = {
  text: string;
  type: "command" | "output" | "comment";
  style?: LogStyleName;
  isActive: boolean;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Resolve an OutputLine to its text and style name. */
export function resolveOutputLine(line: OutputLine): {
  text: string;
  style: LogStyleName;
} {
  if (typeof line === "string") {
    return { text: line, style: "dim" };
  }
  return line;
}
