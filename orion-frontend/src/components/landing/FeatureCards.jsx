import './FeatureCards.css';

const features = [
  {
    icon: '🛡️',
    title: 'Safety Evaluation',
    description: 'Collision detection, TTC analysis, and emergency response metrics — scored in real-time across every scenario.',
  },
  {
    icon: '📋',
    title: 'Compliance Metrics',
    description: 'Speed limit adherence, traffic rule validation, and regulatory compliance scoring based on configurable rule sets.',
  },
  {
    icon: '⚖️',
    title: 'Stability Analysis',
    description: 'Jerk minimization, lane keeping smoothness, and ride comfort evaluation through advanced physics simulation.',
  },
  {
    icon: '⚡',
    title: 'Reactivity Testing',
    description: 'Brake response time, obstacle avoidance latency, and decision-making speed under dynamic traffic conditions.',
  },
];

export default function FeatureCards() {
  return (
    <section className="features section" id="features">
      <h2 className="section-title animate-fade-in-up">
        Four Pillars of <span className="gradient-text">Robustness</span>
      </h2>
      <p className="section-subtitle animate-fade-in-up delay-100">
        Every autonomous driving model is evaluated across four critical dimensions.
      </p>

      <div className="features-grid">
        {features.map((f, i) => (
          <div key={f.title} className={`glass-card feature-card animate-fade-in-up delay-${(i + 1) * 100}`} id={`feature-${i}`}>
            <div className="feature-icon">{f.icon}</div>
            <h3 className="feature-title">{f.title}</h3>
            <p className="feature-desc">{f.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
