"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import type { Group } from "three";
import { BufferGeometry, Float32BufferAttribute } from "three";

const NODES: Array<[number, number, number]> = [
  [0, 0.15, 0],
  [1.15, 0.55, 0.15],
  [-1.05, 0.45, -0.2],
  [0.45, -0.85, 0.4],
  [-0.7, -0.55, -0.45],
  [1.25, -0.15, -0.55],
  [-1.25, -0.05, 0.45],
  [0.15, 1.05, -0.15],
];

function Constellation() {
  const group = useRef<Group>(null);
  const lines = useMemo(() => {
    const positions: number[] = [];
    for (let i = 0; i < NODES.length; i++) {
      for (let j = i + 1; j < NODES.length; j++) {
        const a = NODES[i];
        const b = NODES[j];
        const dx = a[0] - b[0];
        const dy = a[1] - b[1];
        const dz = a[2] - b[2];
        if (dx * dx + dy * dy + dz * dz < 2.6) {
          positions.push(a[0], a[1], a[2], b[0], b[1], b[2]);
        }
      }
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
    return geometry;
  }, []);

  useFrame(({ clock }, dt) => {
    const g = group.current;
    if (!g) return;
    g.rotation.y += dt * 0.16;
    g.rotation.x = Math.sin(clock.elapsedTime * 0.35) * 0.12;
  });

  return (
    <group ref={group}>
      <lineSegments geometry={lines}>
        <lineBasicMaterial color="#c4b5fd" transparent opacity={0.55} />
      </lineSegments>
      {NODES.map((position, index) => (
        <mesh key={index} position={position}>
          <icosahedronGeometry args={[index === 0 ? 0.26 : 0.11, 1]} />
          <meshStandardMaterial
            color={index === 0 ? "#fb7185" : "#8b5cf6"}
            emissive={index === 0 ? "#fb7185" : "#5b21b6"}
            emissiveIntensity={0.35}
            roughness={0.4}
            metalness={0.12}
          />
        </mesh>
      ))}
    </group>
  );
}

export function HeroScene({ active, dpr }: { active: boolean; dpr: number }) {
  return (
    <Canvas
      dpr={dpr}
      frameloop={active ? "always" : "never"}
      camera={{ position: [0, 0, 3.6], fov: 42 }}
      gl={{
        antialias: dpr > 1,
        alpha: true,
        powerPreference: "low-power",
        stencil: false,
        depth: true,
      }}
      onCreated={({ gl }) => {
        gl.setClearColor(0x000000, 0);
      }}
    >
      <ambientLight intensity={0.75} />
      <directionalLight position={[2.2, 2.4, 3]} intensity={1.15} />
      <Constellation />
    </Canvas>
  );
}
