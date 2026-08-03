export const motionTokens = {
  duration: {
    instant: 0.12,
    quick: 0.18,
    base: 0.28,
    state: 0.36,
    route: 0.62,
    chapter: 1
  },
  easing: {
    enter: [0.16, 1, 0.3, 1] as const,
    exit: [0.7, 0, 0.84, 0] as const,
    standard: [0.2, 0.8, 0.2, 1] as const,
    editorial: [0.77, 0, 0.175, 1] as const
  },
  spring: {
    micro: { type: "spring" as const, stiffness: 500, damping: 36 },
    layout: { type: "spring" as const, stiffness: 300, damping: 30 },
    drawer: { type: "spring" as const, stiffness: 220, damping: 26 }
  },
  distance: { xs: 8, sm: 16, md: 32, lg: 64 },
  stagger: { tight: 0.03, base: 0.055, editorial: 0.09 },
  scale: { press: 0.98, hover: 1.015 },
  blur: { reveal: 12, overlay: 20 }
} as const;

export const routeVariants = {
  initial: { opacity: 0, y: 24, filter: "blur(8px)" },
  animate: { opacity: 1, y: 0, filter: "blur(0px)" },
  exit: { opacity: 0, y: -16, filter: "blur(6px)" }
};
