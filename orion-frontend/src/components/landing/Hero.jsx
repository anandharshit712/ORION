import { useRef, useMemo, useEffect } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Points, PointMaterial } from '@react-three/drei';
import * as THREE from 'three';
import './Hero.css';
import { Link } from 'react-router-dom';

// Shared mouse position ref (normalized -1 to 1)
const mouse = { x: 0, y: 0 };

// ── Rotating star field ───────────────────────────────────────────────────
function StarField({ count = 4000 }) {
  const ref = useRef();
  const currentPos = useRef({ x: 0, y: 0 });

  const positions = useMemo(() => {
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      // Expanded range so edges aren't visible during parallax shift
      pos[i * 3]     = (Math.random() - 0.5) * 40; 
      pos[i * 3 + 1] = (Math.random() - 0.5) * 40;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 40;
    }
    return pos;
  }, [count]);

  useFrame((_, delta) => {
    if (ref.current) {
      ref.current.rotation.x -= delta * 0.012;
      ref.current.rotation.y -= delta * 0.018;

      // Subtle parallax for background (moves opposite to foreground)
      currentPos.current.x += (mouse.x * -1.2 - currentPos.current.x) * 0.02;
      currentPos.current.y += (mouse.y * -1.2 - currentPos.current.y) * 0.02;
      
      ref.current.position.x = currentPos.current.x;
      ref.current.position.y = currentPos.current.y;
    }
  });

  return (
    <group rotation={[0, 0, Math.PI / 5]}>
      <Points ref={ref} positions={positions} stride={3} frustumCulled={false}>
        <PointMaterial
          transparent
          color="#a78bfa"
          size={0.022}
          sizeAttenuation
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </Points>
    </group>
  );
}

// ── Slowly drifting + cursor-tracking ORION constellation ─────────────────
function OrionConstellation() {
  const groupRef   = useRef();
  const starRefs   = useRef([]);
  const targetPos  = useRef({ x: 0, y: 0 });
  const currentPos = useRef({ x: 0, y: 0 });
  const { viewport } = useThree();

  // Spread wider horizontally to fit the screen width, while reducing the vertical bounds
  const stars = useMemo(() => [
    [0,    3.6,  0],   
    [6.5,  3.0,  0],   
    [2.5,  1.5,  0],   
    [-3.5, 1.8,  0],   
    [0,    0.6,  0],   
    [2.8, -0.4,  0],   
    [-6.0,-3.2,  0],  
    [6.5, -3.0,  0],  
  ], []);

  const connections = [[0,2],[0,3],[1,2],[3,4],[4,5],[3,6],[5,7],[2,5]];

  useFrame((state) => {
    const t = state.clock.elapsedTime;

    // Subtle parallax mapping to cursor
    const parallaxX = mouse.x * viewport.width  * 0.04;
    const parallaxY = mouse.y * viewport.height * 0.04;

    // Combine sine drift + mouse parallax as target
    targetPos.current.x = Math.sin(t * 0.12) * 0.4 + parallaxX;
    targetPos.current.y = Math.sin(t * 0.17) * 0.3 + parallaxY;

    // Smoothly lerp current towards target (lazy follow)
    currentPos.current.x += (targetPos.current.x - currentPos.current.x) * 0.04;
    currentPos.current.y += (targetPos.current.y - currentPos.current.y) * 0.04;

    if (groupRef.current) {
      groupRef.current.position.x = currentPos.current.x;
      groupRef.current.position.y = currentPos.current.y;
      groupRef.current.rotation.z = Math.sin(t * 0.08) * 0.05 + mouse.x * -0.02;
      groupRef.current.rotation.y = Math.sin(t * 0.10) * 0.05 + mouse.x * 0.04;
    }

    // Per-star pulse
    starRefs.current.forEach((mesh, i) => {
      if (mesh) {
        const pulse = 1 + Math.sin(t * 1.2 + i * 0.9) * 0.15;
        mesh.scale.setScalar(pulse);
      }
    });
  });

  // Position it slightly behind with Z=-2, but the large coordinates will fill the screen
  return (
    <group ref={groupRef} position={[0, 0, -2]}>
      {stars.map((pos, i) => (
        <mesh key={i} position={pos} ref={el => starRefs.current[i] = el}>
          <sphereGeometry args={[0.12, 32, 32]} />
          <meshBasicMaterial color="#c4b5fd" transparent opacity={0.95} />
          <pointLight color="#7c3aed" intensity={0.8} distance={4} />
        </mesh>
      ))}

      {connections.map(([a, b], i) => {
        const start = new THREE.Vector3(...stars[a]);
        const end   = new THREE.Vector3(...stars[b]);
        const mid   = start.clone().add(end).multiplyScalar(0.5);
        const dir   = end.clone().sub(start);
        const len   = dir.length();
        const quat  = new THREE.Quaternion().setFromUnitVectors(
          new THREE.Vector3(0, 1, 0), dir.normalize()
        );
        return (
          <mesh key={`line-${i}`} position={mid} quaternion={quat}>
            <cylinderGeometry args={[0.008, 0.008, len, 6]} />
            <meshBasicMaterial color="#8b5cf6" transparent opacity={0.4} />
          </mesh>
        );
      })}
    </group>
  );
}

// ── Hero ──────────────────────────────────────────────────────────────────
export default function Hero() {
  // Track mouse position globally for the canvas
  useEffect(() => {
    const handleMouseMove = (e) => {
      // Normalize to -1..1 relative to viewport center
      mouse.x =  (e.clientX / window.innerWidth  - 0.5) * 2;
      mouse.y = -(e.clientY / window.innerHeight - 0.5) * 2;
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  return (
    <section className="hero" id="hero">
      <div className="hero-canvas">
        <Canvas camera={{ position: [0, 0, 8], fov: 60 }} gl={{ antialias: true }}>
          <ambientLight intensity={0.05} />
          <StarField />
          <OrionConstellation />
        </Canvas>
      </div>

      <div className="hero-content animate-fade-in-up">
        <div className="hero-badge">◆ Autonomous Driving Evaluation Platform</div>
        <h1 className="hero-title">
          Test Smarter.<br />
          <span className="gradient-text">Drive Safer.</span>
        </h1>
        <p className="hero-description">
          ORION evaluates autonomous driving models across safety, compliance,
          stability, and reactivity — powered by physics-grade simulation and
          real-time analytics.
        </p>
        <div className="hero-actions">
          <Link to="/signup" className="btn btn-primary btn-lg" id="hero-cta">
            Start Evaluating
          </Link>
          <a href="#features" className="btn btn-secondary btn-lg">
            Explore Features
          </a>
        </div>
      </div>

      <div className="hero-gradient-orb hero-orb-1"></div>
      <div className="hero-gradient-orb hero-orb-2"></div>
    </section>
  );
}
