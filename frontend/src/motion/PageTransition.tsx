import { motion } from "motion/react";
import { motionTokens, routeVariants } from "./tokens";

export function PageTransition({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <motion.main
      id="page-content"
      tabIndex={-1}
      className={className}
      variants={routeVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={{ duration: motionTokens.duration.route, ease: motionTokens.easing.enter }}
    >
      {children}
    </motion.main>
  );
}
