import Icon from '../common/Icon';
import './FeatureCards.css';

const features = [
  {
    icon: 'warning',
    title: 'Safety Evaluation',
    weight: '0.50',
    description: 'Collision detection, time-to-collision analysis, and emergency response — scored deterministically across every run.',
  },
  {
    icon: 'check',
    title: 'Compliance Metrics',
    weight: '0.20',
    description: 'Speed-limit adherence, lane keeping, and traffic-rule validation against configurable rule sets.',
  },
  {
    icon: 'overview',
    title: 'Stability Analysis',
    weight: '0.15',
    description: 'Jerk minimization, control smoothness, and ride-comfort evaluation through physics-grade simulation.',
  },
  {
    icon: 'play',
    title: 'Reactivity Testing',
    weight: '0.15',
    description: 'Brake-response latency, obstacle-avoidance timing, and decision speed under dynamic traffic threats.',
  },
];

export default function FeatureCards() {
  return (
    <section className="features section" id="features">
      <div className="features-head animate-reveal">
        <span className="features-idx mono-label">02 / METRIC AXES</span>
        <h2 className="features-title">
          Four pillars of <span className="em">robustness</span>
        </h2>
        <p className="features-sub">
          Every policy is scored across four weighted dimensions, combined into a single
          composite verdict.
        </p>
      </div>

      <div className="features-grid">
        {features.map((f, i) => (
          <div
            key={f.title}
            className={`panel feature-card animate-reveal delay-${i + 1}`}
            id={`feature-${i}`}
          >
            <div className="feature-top">
              <span className="feature-icon" aria-hidden="true">
                <Icon name={f.icon} size={20} />
              </span>
              <span className="feature-no mono-label num">{String(i + 1).padStart(2, '0')}</span>
            </div>
            <h3 className="feature-title">{f.title}</h3>
            <p className="feature-desc">{f.description}</p>
            <div className="feature-foot">
              <span className="mono-label">Weight</span>
              <span className="num feature-weight">{f.weight}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
