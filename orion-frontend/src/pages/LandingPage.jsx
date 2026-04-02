import Navbar from '../components/common/Navbar';
import Hero from '../components/landing/Hero';
import FeatureCards from '../components/landing/FeatureCards';
import StatsSection from '../components/landing/StatsSection';
import Footer from '../components/landing/Footer';

export default function LandingPage() {
  return (
    <>
      <Navbar transparent />
      <Hero />
      <FeatureCards />
      <StatsSection />
      <Footer />
    </>
  );
}
