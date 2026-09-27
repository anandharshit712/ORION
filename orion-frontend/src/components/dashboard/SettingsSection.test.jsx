// Settings section + InfoHint.
//
// Per CLAUDE.md §9, test what fails *silently*. Two things here qualify.
//
// The API key is returned in plaintext exactly once and never again. A UI that
// drops it, truncates it, or shows a copy button that quietly failed costs the
// customer a credential they cannot re-read — and none of that looks broken on
// screen.
//
// The cost hint is hover-only by product decision. Hover-only is precisely the
// interaction a keyboard user never triggers, so what is pinned is that it is
// reachable by focus and announced to a screen reader — and that it quotes no
// price, which is the part of the decision a future edit would erode.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import SettingsSection from './SettingsSection';
import InfoHint from '../common/InfoHint';
import { api } from '../../services/api';

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: {
      username: 'harshit',
      email: 'info@beamhash.com',
      role: 'owner',
      email_verified: true,
    },
  }),
}));

vi.mock('../../theme/ThemeContext', () => ({
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn(), toggleTheme: vi.fn() }),
}));

const ORG = {
  id: 'org-1',
  name: 'Beamhash',
  slug: 'beamhash',
  plan: 'pro',
  run_credits: 500,
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('API keys', () => {
  it('shows the plaintext key once, in full, with the warning that it will not be repeated', async () => {
    const SECRET = 'orion_sk_live_0123456789abcdef0123456789abcdef';
    vi.spyOn(api, 'getOrg').mockResolvedValue(ORG);
    vi.spyOn(api, 'listApiKeys').mockResolvedValue([]);
    vi.spyOn(api, 'createApiKey').mockResolvedValue({ plaintext: SECRET });

    render(<SettingsSection />);
    await screen.findByText(/no api keys/i);

    fireEvent.change(screen.getByPlaceholderText('ci-pipeline'), {
      target: { value: 'ci' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create key/i }));

    // In full: a truncated secret cannot be copied by hand, and the server
    // keeps only a hash.
    expect(await screen.findByText(SECRET)).toBeInTheDocument();
    expect(screen.getByText(/only time orion will show this key/i)).toBeInTheDocument();
  });

  it('says so when the clipboard refuses, instead of looking like it worked', async () => {
    // Clipboard access throws outside a secure context. A button that silently
    // did nothing would lose a key that cannot be read again.
    const SECRET = 'orion_sk_live_deadbeef';
    vi.spyOn(api, 'getOrg').mockResolvedValue(ORG);
    vi.spyOn(api, 'listApiKeys').mockResolvedValue([]);
    vi.spyOn(api, 'createApiKey').mockResolvedValue({ plaintext: SECRET });

    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
    });

    render(<SettingsSection />);
    await screen.findByText(/no api keys/i);
    fireEvent.change(screen.getByPlaceholderText('ci-pipeline'), {
      target: { value: 'ci' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create key/i }));
    await screen.findByText(SECRET);

    fireEvent.click(screen.getByRole('button', { name: /^copy$/i }));

    expect(await screen.findByText(/could not copy/i)).toBeInTheDocument();
  });

  it('reports a failed creation instead of leaving the form looking idle', async () => {
    vi.spyOn(api, 'getOrg').mockResolvedValue(ORG);
    vi.spyOn(api, 'listApiKeys').mockResolvedValue([]);
    vi.spyOn(api, 'createApiKey').mockRejectedValue(new Error('Insufficient role'));

    render(<SettingsSection />);
    await screen.findByText(/no api keys/i);
    fireEvent.change(screen.getByPlaceholderText('ci-pipeline'), {
      target: { value: 'ci' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create key/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/insufficient role/i);
  });

  it('offers revoke only for a key that is still active', async () => {
    vi.spyOn(api, 'getOrg').mockResolvedValue(ORG);
    vi.spyOn(api, 'listApiKeys').mockResolvedValue([
      { id: 'k1', label: 'live', key_prefix: 'orion_ab', created_at: null, revoked_at: null },
      { id: 'k2', label: 'old', key_prefix: 'orion_cd', created_at: null, revoked_at: '2026-01-01T00:00:00' },
    ]);

    render(<SettingsSection />);
    await screen.findByText('live');

    expect(screen.getAllByRole('button', { name: /revoke/i })).toHaveLength(1);
  });
});

describe('Organisation panel', () => {
  it('renders unlimited credits as a word, not as -1', async () => {
    // -1 is OrganisationRepository.UNLIMITED_CREDITS. Printed raw it reads as
    // a negative balance, which is the opposite of what it means.
    vi.spyOn(api, 'getOrg').mockResolvedValue({ ...ORG, run_credits: -1 });
    vi.spyOn(api, 'listApiKeys').mockResolvedValue([]);

    render(<SettingsSection />);

    expect(await screen.findByText(/unlimited/i)).toBeInTheDocument();
    expect(screen.queryByText('-1')).not.toBeInTheDocument();
  });

  it('shows an error for the org panel without breaking the keys panel', async () => {
    // Two independent fetches. One failing must not blank the other.
    vi.spyOn(api, 'getOrg').mockRejectedValue(new Error('org unavailable'));
    vi.spyOn(api, 'listApiKeys').mockResolvedValue([]);

    render(<SettingsSection />);

    expect(await screen.findByText(/org unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/no api keys/i)).toBeInTheDocument();
  });
});

describe('InfoHint', () => {
  it('is reachable by keyboard, not hover alone', async () => {
    render(<InfoHint text="A larger budget searches harder and costs more." />);

    const trigger = screen.getByRole('button', { name: /more information/i });
    fireEvent.focus(trigger);

    await waitFor(() => {
      expect(trigger).toHaveAttribute('aria-expanded', 'true');
    });
  });

  it('describes its control, so the hint is announced rather than orphaned', () => {
    render(<InfoHint text="A larger budget searches harder and costs more." />);

    const trigger = screen.getByRole('button', { name: /more information/i });
    const tooltip = screen.getByRole('tooltip');

    expect(trigger.getAttribute('aria-describedby')).toBe(tooltip.id);
  });

  it('quotes no price', () => {
    // The product decision was to signal that cost rises, with no estimate and
    // no numbers. A number next to an input reads as a quote.
    render(<InfoHint text="A larger budget searches harder and costs more." />);

    const text = screen.getByRole('tooltip').textContent;
    expect(text).not.toMatch(/\d/);
    expect(text).not.toMatch(/credit|\$|price|cost \d/i);
  });
});
