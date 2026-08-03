import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { MotionSystemProvider } from "./motion/MotionSystem";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MotionSystemProvider>
      <App />
    </MotionSystemProvider>
  </StrictMode>
);

if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}
