import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import LandingPage from './pages/LandingPage';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import VerifyEmailPage from './pages/VerifyEmailPage';
import BillingPage from './pages/BillingPage';
import DashboardPage from './pages/DashboardPage';
import SimulationViewer from './components/simulation/SimulationViewer';
import NotFoundPage from './pages/NotFoundPage';
import RunPage from './pages/RunPage';

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-screen">Authenticating…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      {/* Public: the verification email is opened in whatever browser the
          customer happens to be in, which may have no session. */}
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route
        path="/dashboard/*"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      {/* More specific than /dashboard/*, which React Router v6 ranks by
          specificity rather than order. A single run gets a real URL because
          it is a thing people link each other to — unlike the dashboard's
          list sections, which are view state. */}
      <Route
        path="/dashboard/runs/:runId"
        element={
          <ProtectedRoute>
            <RunPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/billing"
        element={
          <ProtectedRoute>
            <BillingPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/simulation/:runId"
        element={
          <ProtectedRoute>
            <SimulationViewer />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
