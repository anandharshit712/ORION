// ORION — BillingPage  [Phase 1.4]
// Route: /billing
// Live plan + usage from the API, Stripe hosted checkout, Stripe customer portal.
// See docs/UI_DESIGN.md §11.4.
//
// Plan allocations are fetched, never hardcoded: this page used to advertise
// 100 / 2,500 / 15,000 run credits against a backend that granted 50 / 500 /
// 3,000 — the kind of mismatch a customer discovers on their first invoice.

import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import PlanCard from '../components/billing/PlanCard';
import UsageBar from '../components/billing/UsageBar';
import AlertBanner from '../components/common/AlertBanner';
import './BillingPage.css';

// Marketing copy stays here; the numbers come from the API.
const PLAN_FEATURES = {
  free: ['Built-in models', 'Single-run streaming', 'Community support'],
  starter: ['Model uploads (SDK)', 'Async batch queue', 'All scenario categories', 'Email support'],
  pro: ['Docker model registration', 'Adversarial search', 'Priority support'],
  enterprise: ['On-prem / VPC deploy', 'SSO + audit logs', 'Dedicated SLA'],
};

const TITLE = { free: 'Free', starter: 'Starter', pro: 'Pro', enterprise: 'Enterprise' };

export default function BillingPage() {
  const [plans, setPlans] = useState([]);
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([api.getPlans(), api.getBillingUsage()])
      .then(([planList, usageData]) => {
        if (cancelled) return;
        setPlans(planList);
        setUsage(usageData);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Could not load billing');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, []);

  const billingActive = usage?.billing_active === true;
  const currentPlan = usage?.plan ?? 'free';

  const handleSelect = async (planName) => {
    setPending(planName);
    setError(null);
    try {
      const origin = window.location.origin;
      const { checkout_url: url } = await api.createCheckout(
        planName,
        `${origin}/billing?checkout=success`,
        `${origin}/billing?checkout=cancelled`,
      );
      // Full navigation, not fetch: Checkout is a Stripe-hosted page, which is
      // what keeps card details off this origin entirely.
      window.location.href = url;
    } catch (err) {
      setError(err.message || 'Could not start checkout');
      setPending(null);
    }
  };

  const handlePortal = async () => {
    setPending('portal');
    setError(null);
    try {
      const { checkout_url: url } = await api.openBillingPortal(
        `${window.location.origin}/billing`,
      );
      window.location.href = url;
    } catch (err) {
      setError(err.message || 'Could not open the billing portal');
      setPending(null);
    }
  };

  if (loading) {
    return (
      <div className="billing-page" id="billing-page">
        <div className="panel skeleton" style={{ height: 120 }} />
      </div>
    );
  }

  // Credits are a remaining balance, not a consumption count. Showing "used"
  // would need a period starting balance the backend does not track yet, so the
  // bar is filled by what is left.
  const creditsRemaining = usage?.credits_unlimited ? null : (usage?.run_credits ?? 0);
  const planAllocation = plans.find((p) => p.name === currentPlan)?.run_credits ?? 0;

  return (
    <div className="billing-page" id="billing-page">
      <header className="billing-head">
        <div>
          <h1>Billing</h1>
          <div className="billing-sub mono-label">
            PLAN={String(currentPlan).toUpperCase()} · {billingActive ? 'ACTIVE' : 'BETA'}
            {usage?.subscription_status ? ` · ${usage.subscription_status.toUpperCase()}` : ''}
          </div>
        </div>
        {billingActive && (
          <button
            className="btn-ghost"
            onClick={handlePortal}
            disabled={pending !== null}
            id="billing-portal"
          >
            {pending === 'portal' ? 'Opening…' : 'Manage subscription'}
          </button>
        )}
      </header>

      {error && (
        <AlertBanner severity="error" title="Billing error" message={error} />
      )}

      {!billingActive && (
        <AlertBanner
          severity="info"
          title="Billing in beta"
          message="Self-serve billing is not enabled for this environment. Credits are provisioned manually during the beta — contact support to adjust your plan."
        />
      )}

      <div className="panel billing-usage">
        <div className="billing-usage-cap mono-label">Current Usage</div>
        {usage?.credits_unlimited ? (
          <p className="num">Unlimited run credits</p>
        ) : (
          <UsageBar
            used={creditsRemaining}
            total={Math.max(planAllocation, creditsRemaining)}
            label="Run credits remaining"
          />
        )}
        {usage?.next_renewal && (
          <div className="mono-label">
            Renews {new Date(usage.next_renewal).toLocaleDateString()}
          </div>
        )}
      </div>

      <div className="billing-plans">
        {plans.map((plan) => (
          <PlanCard
            key={plan.name}
            name={TITLE[plan.name] ?? plan.name}
            price={plan.monthly_usd === null ? 'Custom' : plan.monthly_usd}
            features={[
              plan.credits_unlimited
                ? 'Unlimited run credits'
                : `${plan.run_credits.toLocaleString()} run credits / mo`,
              ...(PLAN_FEATURES[plan.name] ?? []),
            ]}
            featured={plan.name === 'pro'}
            current={plan.name === currentPlan}
            // Free needs no checkout and Enterprise is negotiated, so neither
            // has a self-serve price — the backend 400s on both.
            disabled={!billingActive || !plan.self_serve || pending !== null}
            ctaLabel={
              plan.name === currentPlan
                ? 'Current Plan'
                : !plan.self_serve
                  ? 'Contact sales'
                  : pending === plan.name
                    ? 'Redirecting…'
                    : 'Select Plan'
            }
            onSelect={() => handleSelect(plan.name)}
          />
        ))}
      </div>
    </div>
  );
}
