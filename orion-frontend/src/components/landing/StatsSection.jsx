import { useState, useEffect, useRef } from 'react';
import './StatsSection.css';

function prefersReducedMotion() {
  return typeof window !== 'undefined' &&
    window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function AnimatedCounter({ end, duration = 1600, decimals = 0 }) {
  const [count, setCount] = useState(prefersReducedMotion() ? end : 0);
  const ref = useRef(null);
  const started = useRef(false);

  useEffect(() => {
    if (prefersReducedMotion()) { setCount(end); return; }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !started.current) {
          started.current = true;
          const start = performance.now();
          const animate = (now) => {
            const progress = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
            setCount(eased * end);
            if (progress < 1) requestAnimationFrame(animate);
          };
          requestAnimationFrame(animate);
        }
      },
      { threshold: 0.3 }
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [end, duration]);

  return <span ref={ref}>{count.toFixed(decimals)}</span>;
}

const stats = [
  { value: 50, unit: 'Hz', label: 'Fixed Timestep' },
  { value: 0.02, decimals: 2, unit: 's', label: 'Deterministic dt' },
  { value: 6, label: 'Scenario Classes' },
  { value: 4, label: 'Metric Axes' },
];

export default function StatsSection() {
  return (
    <section className="stats-section" id="stats">
      <div className="stats-inner">
        <div className="stats-head">
          <span className="stats-idx mono-label">03 / DETERMINISM</span>
          <h2 className="stats-title">
            Same seed in, same score out.<span className="em"> Every time.</span>
          </h2>
        </div>

        <div className="spec-strip stats-grid">
          {stats.map((s, i) => (
            <div key={s.label} className="stat-item" id={`stat-${i}`}>
              <div className="v num">
                <AnimatedCounter end={s.value} decimals={s.decimals || 0} />
                {s.unit && <small>{s.unit}</small>}
              </div>
              <div className="k">{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
