// ORION — InfoHint  (docs/UI_DESIGN.md §9.15)
//
// A small "i" that reveals one line of context on hover or focus. Introduced
// for the adversarial-search budget field, where the product decision was to
// signal that a bigger budget costs more **without quoting a price** — no
// estimate, no numbers, because a number shown next to an input reads as a
// quote and this one would be wrong the moment plan pricing changes.
//
// Deliberately not a tooltip library and not a popover: no positioning engine,
// no portal, no dismiss logic. It is one line of text next to one control.
//
// Keyboard and screen readers get it for free rather than as an afterthought:
// the trigger is a real <button> (focusable, so the hint appears on Tab), the
// text is always in the DOM with `role="tooltip"`, and the button points at it
// with aria-describedby. A hover-only div would be invisible to both.

import { useId, useState } from 'react';
import './InfoHint.css';

/**
 * InfoHint
 *
 * @param text   string  one short line; keep it to a sentence
 * @param label  string  accessible name for the trigger
 */
export default function InfoHint({ text, label = 'More information' }) {
  const id = useId();
  const [open, setOpen] = useState(false);

  return (
    <span className="info-hint">
      <button
        type="button"
        className="info-hint__trigger"
        aria-label={label}
        aria-describedby={id}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        // A hint is not an action. Clicking must not submit the form it sits
        // inside, which a button without an onClick handler still would if the
        // type were not explicitly "button".
        onClick={(e) => e.preventDefault()}
      >
        i
      </button>
      <span
        id={id}
        role="tooltip"
        className={`info-hint__bubble ${open ? 'is-open' : ''}`}
      >
        {text}
      </span>
    </span>
  );
}
