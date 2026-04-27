// ORION — BillingPage  [P1]
// Route: /dashboard/billing
// Current plan, usage, upgrade via Stripe
// TODO [P1]: Implement this page.

import React from 'react';
import { useAuth } from '../context/AuthContext';
import './BillingPage.css';

/**
 * BillingPage — Current plan, usage, upgrade via Stripe
 */
export default function BillingPage() {
  const { user } = useAuth();

  return (
    <div className="BillingPage">
      <h1>BillingPage</h1>
      {/* TODO [P1]: Implement BillingPage */}
      <p style={{ color: '#888' }}>BillingPage — not yet implemented [P1]</p>
    </div>
  );
}
