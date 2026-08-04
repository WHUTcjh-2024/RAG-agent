import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { MotionConfig, useReducedMotion } from "motion/react";
import { motionTokens } from "./tokens";

type MotionCapability = "full" | "balanced" | "reduced";

const MotionContext = createContext<{ capability: MotionCapability; reduced: boolean }>({
  capability: "balanced",
  reduced: false
});

function detectCapability(): MotionCapability {
  const memory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory || 4;
  const cores = navigator.hardwareConcurrency || 4;
  const compact = window.matchMedia("(max-width: 760px)").matches;
  if (compact || memory <= 4 || cores <= 4) return "balanced";
  return "full";
}

export function MotionSystemProvider({ children }: { children: React.ReactNode }) {
  const prefersReduced = useReducedMotion() || false;
  const [capability, setCapability] = useState<MotionCapability>(() => detectCapability());

  useEffect(() => {
    const query = window.matchMedia("(max-width: 760px)");
    const update = () => setCapability(detectCapability());
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const updateVisibility = () => {
      document.documentElement.dataset.pageVisible = String(!document.hidden);
    };
    updateVisibility();
    document.addEventListener("visibilitychange", updateVisibility);
    return () => document.removeEventListener("visibilitychange", updateVisibility);
  }, []);

  const value = useMemo(
    () => ({ capability: prefersReduced ? "reduced" as const : capability, reduced: prefersReduced }),
    [capability, prefersReduced]
  );

  return (
    <MotionContext.Provider value={value}>
      <MotionConfig
        reducedMotion="user"
        transition={{ duration: motionTokens.duration.base, ease: motionTokens.easing.enter }}
      >
        {children}
      </MotionConfig>
    </MotionContext.Provider>
  );
}

export const useMotionSystem = () => useContext(MotionContext);
