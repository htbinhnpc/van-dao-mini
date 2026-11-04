import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { DashboardBoundary } from "./components";
import "./style.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <DashboardBoundary><App /></DashboardBoundary>
  </React.StrictMode>,
);
