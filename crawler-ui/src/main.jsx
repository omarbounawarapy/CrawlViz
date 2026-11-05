import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./global.css";
import Root from "./Root.jsx";
import { ErrorBoundary } from "./features/errors";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <ErrorBoundary>
      <Root />
    </ErrorBoundary>
  </StrictMode>,
);
