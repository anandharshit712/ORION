// ORION — HudBar
// Sticky top status strip for authed surfaces. See ORION_UI_DESIGN.md §6.1.

import { useState, useEffect } from 'react';
import { BUILD_HASH } from '../../utils/constants';
import ThemeToggle from './ThemeToggle';
import './HudBar.css';

function utcClock() {
  // HH:MM:SS UTC — sim code uses world.sim_time; this is wall-clock chrome only.
  return new Date().toUTCString().slice(17, 25);
}

export default function HudBar({ status = 'SYSTEM NOMINAL', seed = null }) {
  const [clock, setClock] = useState(utcClock);

  useEffect(() => {
    const id = setInterval(() => setClock(utcClock()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="hud" role="banner">
      <span className="hud-brand">
        <span className="hud-dot" aria-hidden="true" />
        ORION<b>//</b>AREP
      </span>
      <span className="hud-stat">
        <span className="live-dot blink" aria-hidden="true" />
        {status}
      </span>
      <span className="hud-sep" />
      {seed != null && (
        <span className="hud-stat hud-hide-sm">
          SEED&nbsp;<b className="hud-cyan num">{seed}</b>
        </span>
      )}
      <span className="hud-stat hud-hide-sm">
        BUILD&nbsp;<b className="hud-mute">{BUILD_HASH}</b>
      </span>
      <span className="hud-stat hud-hide-sm num">{clock} UTC</span>
      <span className="hud-kbd hud-hide-sm">⌘K</span>
      <ThemeToggle />
    </header>
  );
}
