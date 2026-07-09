import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import './Hero.css';

const GAUGE_R = 72;
const GAUGE_CIRC = 2 * Math.PI * GAUGE_R; // ≈ 452.4
const GAUGE_TARGET = 94.2; // composite score (demo telemetry)

// Cyan sparkline sample series (0–100) — drawn as a normalized polyline.
const SPARK = [22, 18, 30, 26, 44, 38, 60, 50, 72, 40, 66, 58, 80, 74, 90, 86];

function prefersReducedMotion() {
  return typeof window !== 'undefined' &&
    window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// ── Reticle composite gauge (SVG ring + amber progress arc + cardinal ticks) ─
function ReticleGauge() {
  const [value, setValue] = useState(prefersReducedMotion() ? GAUGE_TARGET : 0);

  useEffect(() => {
    if (prefersReducedMotion()) return;
    let raf;
    const start = performance.now();
    const duration = 900;
    const tick = (now) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(eased * GAUGE_TARGET);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const dashoffset = GAUGE_CIRC - GAUGE_CIRC * (value / 100);

  return (
    <div className="reticle" role="img" aria-label={`Composite score ${GAUGE_TARGET.toFixed(1)} of 100`}>
      <svg viewBox="0 0 200 200">
        {/* outer guide ring */}
        <circle cx="100" cy="100" r="86" fill="none" stroke="var(--border-strong)" strokeWidth="1" />
        {/* track */}
        <circle cx="100" cy="100" r={GAUGE_R} fill="none" stroke="var(--bg-inset)" strokeWidth="10" />
        {/* amber progress arc */}
        <circle
          cx="100" cy="100" r={GAUGE_R} fill="none"
          stroke="var(--amber)" strokeWidth="10" strokeLinecap="butt"
          strokeDasharray={GAUGE_CIRC}
          strokeDashoffset={dashoffset}
          transform="rotate(-90 100 100)"
        />
        {/* 4 cardinal ticks */}
        <line x1="100" y1="6" x2="100" y2="20" stroke="var(--tick)" strokeWidth="1.5" />
        <line x1="100" y1="180" x2="100" y2="194" stroke="var(--tick)" strokeWidth="1.5" />
        <line x1="6" y1="100" x2="20" y2="100" stroke="var(--tick)" strokeWidth="1.5" />
        <line x1="180" y1="100" x2="194" y2="100" stroke="var(--tick)" strokeWidth="1.5" />
      </svg>
      <div className="reticle-read">
        <div className="reticle-big num">{value.toFixed(1)}</div>
        <div className="reticle-lbl">Composite Score</div>
      </div>
    </div>
  );
}

// ── Cyan sparkline (inline SVG polyline + amber end marker) ──────────────────
function Sparkline() {
  const w = 100;
  const h = 100;
  const last = SPARK.length - 1;
  const pts = SPARK.map((p, i) => `${(i / last) * w},${h - (p / 100) * h}`).join(' ');
  const lx = w;
  const ly = h - (SPARK[last] / 100) * h;
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts} fill="none" stroke="var(--cyan)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      <rect x={lx - 3} y={ly - 3} width="3.5" height="3.5" fill="var(--amber)" />
    </svg>
  );
}

// ── Hero ─────────────────────────────────────────────────────────────────
export default function Hero() {
  return (
    <section className="hero" id="hero">
      <div className="hero-inner">
        {/* LEFT — pitch */}
        <div className="hero-left">
          <div className="hero-badge animate-reveal mono-label">
            Autonomous Robustness Evaluation Platform
          </div>
          <h1 className="hero-title animate-reveal delay-1">
            Robustness,<br />
            <span className="em">measured.</span>{' '}
            <span className="stroke">not guessed.</span>
          </h1>
          <p className="hero-lead animate-reveal delay-2">
            ORION runs your driving policy through parameterized scenarios hundreds of
            times and returns deterministic, statistically rigorous safety scores.
            A test harness — not a simulator.
          </p>
          <div className="hero-cta animate-reveal delay-3">
            <Link to="/signup" className="btn btn-primary btn-lg" id="hero-cta">
              Start Evaluating <span className="arr">→</span>
            </Link>
            <a href="#features" className="btn btn-ghost btn-lg">
              Explore Platform
            </a>
          </div>
          <div className="spec-strip hero-specs animate-reveal delay-4">
            <div>
              <div className="v num">50<small>Hz</small></div>
              <div className="k">Fixed Timestep</div>
            </div>
            <div>
              <div className="v num">0.02<small>s</small></div>
              <div className="k">dt · Deterministic</div>
            </div>
            <div>
              <div className="v num">6</div>
              <div className="k">Scenario Classes</div>
            </div>
            <div>
              <div className="v num">4</div>
              <div className="k">Metric Axes</div>
            </div>
          </div>
        </div>

        {/* RIGHT — instrument cluster */}
        <div className="panel panel--live instrument animate-reveal delay-2">
          <div className="instr-top">
            <span className="mono-label">LIVE TELEMETRY · EMERGENCYBRAKE</span>
            <span className="instr-rec mono-label">
              <span className="live-dot blink" aria-hidden="true" /> REC
            </span>
          </div>

          <ReticleGauge />

          <div className="spark-wrap">
            <Sparkline />
          </div>

          <div className="instr-rows">
            <div>
              <div className="k">Min TTC</div>
              <div className="v c num">3.42 s</div>
            </div>
            <div>
              <div className="k">Collision</div>
              <div className="v a num">NONE</div>
            </div>
            <div>
              <div className="k">Speed</div>
              <div className="v num">12.4 m/s</div>
            </div>
            <div>
              <div className="k">Verdict</div>
              <div className="v num verdict-pass">PASS</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
