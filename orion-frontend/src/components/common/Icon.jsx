// ORION — Icon set
// Single inline-SVG icon source. Stroke-based, 1.5px, currentColor, sharp joints.
// No emoji as UI icons (ORION_UI_DESIGN.md §7). Add new icons here + list in the doc.

const ICONS = {
  overview: (
    <>
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
    </>
  ),
  scenarios: (
    <>
      <path d="M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z" />
      <path d="M9 3v15M15 6v15" />
    </>
  ),
  runs: (
    <>
      <path d="M5 3v18" />
      <path d="M5 4h13l-3 4 3 4H5" />
    </>
  ),
  models: (
    <>
      <path d="M12 2l9 5v10l-9 5-9-5V7z" />
      <path d="M12 12l9-5M12 12v10M12 12L3 7" />
    </>
  ),
  batches: (
    <>
      <path d="M12 3l9 5-9 5-9-5z" />
      <path d="M3 13l9 5 9-5" />
    </>
  ),
  compare: (
    <>
      <rect x="3" y="4" width="7" height="16" />
      <rect x="14" y="4" width="7" height="16" />
    </>
  ),
  settings: (
    <>
      <line x1="4" y1="7" x2="20" y2="7" />
      <line x1="4" y1="17" x2="20" y2="17" />
      <circle cx="9" cy="7" r="2.3" />
      <circle cx="15" cy="17" r="2.3" />
    </>
  ),
  billing: (
    <>
      <rect x="2" y="5" width="20" height="14" />
      <line x1="2" y1="10" x2="22" y2="10" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.5" y2="16.5" />
    </>
  ),
  key: (
    <>
      <circle cx="8" cy="8" r="4" />
      <path d="M11 11l9 9M16 16l3-3M19 19l2-2" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V4M6 10l6-6 6 6" />
      <path d="M4 20h16" />
    </>
  ),
  download: (
    <>
      <path d="M12 4v12M6 10l6 6 6-6" />
      <path d="M4 20h16" />
    </>
  ),
  play: <path d="M6 4l14 8-14 8z" />,
  refresh: (
    <>
      <path d="M21 12a9 9 0 1 1-3-6.7" />
      <path d="M21 3v5h-5" />
    </>
  ),
  power: (
    <>
      <path d="M12 3v9" />
      <path d="M6.3 6.3a9 9 0 1 0 11.4 0" />
    </>
  ),
  close: (
    <>
      <line x1="5" y1="5" x2="19" y2="19" />
      <line x1="19" y1="5" x2="5" y2="19" />
    </>
  ),
  check: <path d="M4 12l5 6L20 5" />,
  warning: (
    <>
      <path d="M12 3l10 18H2z" />
      <line x1="12" y1="9" x2="12" y2="14" />
      <circle cx="12" cy="17.5" r="0.6" fill="currentColor" />
    </>
  ),
  'chevron-down': <path d="M5 9l7 7 7-7" />,
  'chevron-right': <path d="M9 5l7 7-7 7" />,
  external: (
    <>
      <path d="M14 4h6v6" />
      <path d="M20 4l-9 9" />
      <path d="M19 13v6H5V5h6" />
    </>
  ),
  copy: (
    <>
      <rect x="9" y="9" width="11" height="11" />
      <path d="M5 15V4h11" />
    </>
  ),
};

export default function Icon({ name, size = 18, className = '', strokeWidth = 1.5, ...rest }) {
  const content = ICONS[name];
  if (!content) return null;
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {content}
    </svg>
  );
}

export const ICON_NAMES = Object.keys(ICONS);
