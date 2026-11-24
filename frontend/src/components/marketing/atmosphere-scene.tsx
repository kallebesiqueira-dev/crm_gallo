"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import type { Points } from "three";

function Dust({ count }: { count: number }) {
  const ref = useRef<Points>(null);
  const positions = useMemo(() => {
    const data = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const seed = Math.sin(i * 12.9898) * 43758.5453;
      const a = seed - Math.floor(seed);
      const b = (seed * 1.37) - Math.floor(seed * 1.37);
      const c = (seed * 2.11) - Math.floor(seed * 2.11);
      const radius = 1.2 + a * 4.2;
      const theta = b * Math.PI * 2;
      const y = (c - 0.5) * 3.2;
      data[i * 3] = Math.cos(theta) * radius;
      data[i * 3 + 1] = y;
      data[i * 3 + 2] = Math.sin(theta) * radius * 0.65;
    }
    return data;
  }, [count]);

  useFrame((_, dt) => {
    if (ref.current) ref.current.rotation.y += dt * 0.035;
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        color="#ddd6fe"
        size={0.028}
        sizeAttenuation
        transparent
        opacity={0.75}
        depthWrite={false}
      />
    </points>
  );
}

export function AtmosphereScene({ active, dpr }: { active: boolean; dpr: number }) {
  const count = dpr <= 1 ? 70 : 140;
  return (
    <Canvas
      dpr={dpr}
      frameloop={active ? "always" : "never"}
      camera={{ position: [0, 0, 5.2], fov: 55 }}
      gl={{ antialias: false, alpha: true, powerPreference: "low-power", stencil: false }}
      onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
    >
      <Dust count={count} />
    </Canvas>
  );
}
