import { useState, useEffect, useRef } from 'react';
import './StatsSection.css';

function AnimatedCounter({ end, duration = 2000, suffix = '' }) {
  const [count, setCount] = useState(0);
  const ref = useRef(null);
  const started = useRef(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !started.current) {
          started.current = true;
          const start = performance.now();
          const animate = (now) => {
            const progress = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
            setCount(Math.floor(eased * end));
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

  return <span ref={ref}>{count}{suffix}</span>;
}

const stats = [
  { value: 100, suffix: '+', label: 'Test Scenarios' },
  { value: 4, suffix: '', label: 'Evaluation Pillars' },
  { value: 50, suffix: 'Hz', label: 'Simulation Rate' },
  { value: 99, suffix: '%', label: 'Uptime' },
];

export default function StatsSection() {
  return (
    <section className="stats-section" id="stats">
      <div className="stats-inner section">
        <div className="stats-grid">
          {stats.map((s, i) => (
            <div key={s.label} className="stat-item" id={`stat-${i}`}>
              <div className="stat-value gradient-text">
                <AnimatedCounter end={s.value} suffix={s.suffix} />
              </div>
              <div className="stat-label">{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
