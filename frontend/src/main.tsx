import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
// Bundled via npm (not a CDN <link>) so the version always matches the
// `leaflet` package and the stylesheet can never silently fail to load —
// that mismatch was the cause of the map tiles/lines rendering shifted.
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
