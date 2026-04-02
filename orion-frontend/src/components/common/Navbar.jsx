import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import './Navbar.css';

export default function Navbar({ transparent = false }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <nav className={`navbar ${transparent ? 'navbar-transparent' : ''}`} id="main-navbar">
      <div className="navbar-inner">
        <Link to="/" className="navbar-brand">
          <span className="brand-icon">◆</span>
          <span className="brand-text">ORION</span>
        </Link>

        <div className="navbar-links">
          {user ? (
            <>
              <Link to="/dashboard" className="nav-link">Dashboard</Link>
              <span className="nav-user">{user.username}</span>
              <button onClick={handleLogout} className="btn btn-ghost" id="logout-btn">
                Logout
              </button>
            </>
          ) : (
            <>
              <a href="#features" className="nav-link">Features</a>
              <a href="#stats" className="nav-link">Stats</a>
              <Link to="/login" className="btn btn-secondary" id="login-btn">Login</Link>
              <Link to="/signup" className="btn btn-primary" id="signup-btn">Get Started</Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
