// ORION — ThemeToggle
// The single sanctioned theme control. Used in HudBar / Navbar.

import { useTheme } from '../../theme/ThemeContext';
import './ThemeToggle.css';

export default function ThemeToggle({ className = '' }) {
  const { theme, toggleTheme } = useTheme();
  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <button
      type="button"
      className={`theme-toggle ${className}`}
      onClick={toggleTheme}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
    >
      <span className="theme-toggle-sw" aria-hidden="true" />
      <span className="theme-toggle-label">{theme.toUpperCase()}</span>
    </button>
  );
}
