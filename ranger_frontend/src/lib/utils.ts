// ─── RANGER V3 START: cn helper ───
/**
 * cn() — merge conditional classNames with Tailwind conflict resolution.
 * Standard clsx + tailwind-merge composition. Used by the console primitives
 * so callers can pass overriding classes without specificity fights.
 */
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
// ─── RANGER V3 END: cn helper ───