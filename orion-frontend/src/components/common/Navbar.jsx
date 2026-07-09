import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import ThemeToggle from './ThemeToggle';
import './Navbar.css';

export default function Navbar({ transparent = false }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const solid = !transparent || scrolled;

  return (
    <nav
      className={`navbar ${transparent ? 'navbar-transparent' : ''} ${solid ? 'navbar-solid' : ''}`}
      id="main-navbar"
    >
      <div className="navbar-inner">
        <Link to="/" className="navbar-brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-text">ORION<b>//</b>AREP</span>
        </Link>

        <div className="navbar-links">
          {user ? (
            <>
              <Link to="/dashboard" className="nav-link">Dashboard</Link>
              <span className="nav-user num">{user.username}</span>
              <button onClick={handleLogout} className="btn btn-ghost btn-sm" id="logout-btn">
                Logout
              </button>
              <ThemeToggle />
            </>
          ) : (
            <>
              <a href="#features" className="nav-link">Platform</a>
              <a href="#stats" className="nav-link">Scenarios</a>
              <a href="#features" className="nav-link nav-link-hide-sm">Docs</a>
              <Link to="/login" className="btn btn-ghost btn-sm" id="login-btn">Sign in</Link>
              <Link to="/signup" className="btn btn-primary btn-sm" id="signup-btn">
                Start Evaluating <span className="arr">→</span>
              </Link>
              <ThemeToggle />
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
