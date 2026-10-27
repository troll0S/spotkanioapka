import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Brak elementu #root w index.html");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
