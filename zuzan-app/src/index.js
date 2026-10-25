import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();

// Offline support: keep the app shell available with no signal, and tell the user plainly that nothing can be saved offline.
if (typeof window !== "undefined") {
  if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
    window.addEventListener("load", () => {
      try { navigator.serviceWorker.register("/sw.js").catch(() => {}); } catch (e) { /* ignore */ }
    });
  }
  const bar = document.createElement("div");
  bar.id = "zuzan-offline-bar";
  bar.setAttribute("role", "status");
  bar.textContent = "You are offline. You can look around, but changes cannot be saved until you are back online.";
  bar.style.cssText = "display:none;position:fixed;top:0;left:0;right:0;z-index:99999;background:#92400e;color:#fff;font:600 13px/1.4 system-ui,sans-serif;padding:8px 14px;text-align:center;padding-top:calc(8px + env(safe-area-inset-top,0px));";
  const sync = () => { bar.style.display = navigator.onLine ? "none" : "block"; };
  window.addEventListener("online", sync);
  window.addEventListener("offline", sync);
  const mount = () => { document.body.appendChild(bar); sync(); };
  if (document.body) mount(); else window.addEventListener("DOMContentLoaded", mount);
}
