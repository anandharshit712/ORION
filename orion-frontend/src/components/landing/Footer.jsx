import './Footer.css';

export default function Footer() {
  return (
    <footer className="footer" id="footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <span className="brand-icon">◆</span>
          <span>ORION</span>
        </div>
        <p className="footer-tagline">
          Operational Robustness & Intelligence Optimization Network
        </p>
        <div className="footer-divider"></div>
        <p className="footer-copy">
          © {new Date().getFullYear()} ORION — Built for autonomous driving evaluation.
        </p>
      </div>
    </footer>
  );
}
