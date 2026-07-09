// ORION — BillingPage  [P1]
// Route: /dashboard/billing
// Plans + usage, gated behind beta `billing_enabled` (ORION_UI_DESIGN.md §11.4).
// Visual restyle only. The beta gate reads `billing_enabled` defensively off the
// authed user (off until the backend flag is wired); plan data is presentational
// scaffold (no api.js wiring invented).

import React from 'react';
import { useAuth } from '../context/AuthContext';
import PlanCard from '../components/billing/PlanCard';
import UsageBar from '../components/billing/UsageBar';
import AlertBanner from '../components/common/AlertBanner';
import './BillingPage.css';

// Static plan scaffold (presentational — pricing wiring tracked separately).
const PLANS = [
  {
    name: 'Free',
    price: 0,
    features: ['100 run credits / mo', 'Built-in models', 'Single-run streaming', 'Community support'],
  },
  {
    name: 'Starter',
    price: 49,
    features: ['2,500 run credits / mo', 'Model uploads (SDK)', 'Async batch queue', 'Email support'],
  },
  {
    name: 'Pro',
    price: 199,
    featured: true,
    features: ['15,000 run credits / mo', 'Docker model registration', 'Adversarial search', 'Priority support'],
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    features: ['Unlimited credits', 'On-prem / VPC deploy', 'SSO + audit logs', 'Dedicated SLA'],
  },
];

export default function BillingPage() {
  const { user } = useAuth();

  // Beta gate — keep billing behind the backend `billing_enabled` flag.
  const billingEnabled =
    user?.billing_enabled ??
    user?.organization?.billing_enabled ??
    user?.org?.billing_enabled ??
    false;

  const currentPlan = user?.organization?.plan ?? user?.org?.plan ?? 'Free';
  const creditsUsed = user?.credits_used ?? user?.organization?.credits_used;
  const creditsTotal = user?.credits_total ?? user?.organization?.credits_total;

  return (
    <div className="billing-page" id="billing-page">
      <header className="billing-head">
        <div>
          <h1>Billing</h1>
          <div className="billing-sub mono-label">
            PLAN={String(currentPlan).toUpperCase()} · {billingEnabled ? 'ACTIVE' : 'BETA'}
          </div>
        </div>
      </header>

      {!billingEnabled ? (
        <>
          <AlertBanner
            severity="info"
            title="Billing in beta"
            message="Self-serve billing is not yet enabled for this organization. Credits are provisioned manually during the beta — contact support to adjust your plan."
          />
          <div className="panel billing-locked">
            <span className="mono-label">Plans preview</span>
            <p>Plan selection unlocks once billing is enabled for your organization.</p>
          </div>
        </>
      ) : (
        <>
          <div className="panel billing-usage">
            <div className="billing-usage-cap mono-label">Current Usage</div>
            <UsageBar used={creditsUsed} total={creditsTotal} label="Run Credits · this period" />
          </div>

          <div className="billing-plans">
            {PLANS.map((p) => (
              <PlanCard
                key={p.name}
                name={p.name}
                price={p.price}
                features={p.features}
                featured={p.featured}
                current={String(currentPlan).toLowerCase() === p.name.toLowerCase()}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
