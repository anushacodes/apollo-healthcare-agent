'use strict';

/**
 * api.js — Thin wrapper over the Apollo REST + WebSocket API.
 */

const API = (() => {
  const BASE = '';  // same origin

  async function getCases() {
    const r = await fetch(`${BASE}/api/agent/cases`);
    if (!r.ok) throw new Error(`getCases: ${r.status}`);
    return (await r.json()).cases;
  }

  async function getCaseData(caseKey) {
    const r = await fetch(`${BASE}/api/agent/cases/${caseKey}`);
    if (!r.ok) throw new Error(`getCaseData: ${r.status}`);
    return r.json();
  }

  async function getKgStatus() {
    const r = await fetch(`${BASE}/api/kg/status`);
    if (!r.ok) throw new Error(`getKgStatus: ${r.status}`);
    return r.json();
  }

  async function triggerKgSeed(force = false) {
    const r = await fetch(`${BASE}/api/kg/seed?force=${force}`, { method: 'POST' });
    if (!r.ok) throw new Error(`triggerKgSeed: ${r.status}`);
    return r.json();
  }

  /**
   * Run the agent pipeline over WebSocket.
   * @param {string} patientId
   * @param {Object} payload  — patient data dict or { case: "case_a" }
   * @param {function} onEvent  — called with each parsed JSON event
   * @returns {Promise} resolves when pipeline is done or WS closes
   */
  function runAgentWs(patientId, payload, onEvent) {
    return new Promise((resolve, reject) => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(`${proto}://${location.host}/api/agent/run/${patientId}`);

      ws.onopen = () => ws.send(JSON.stringify(payload));
      ws.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data);
          onEvent(event);
          if (event.node === '__done__' || event.node === '__error__') {
            ws.close();
            resolve(event);
          }
        } catch (err) {
          console.error('[ws] parse error', err);
        }
      };
      ws.onerror = (e) => reject(e);
      ws.onclose = () => resolve(null);
    });
  }

  return { getCases, getCaseData, getKgStatus, triggerKgSeed, runAgentWs };
})();

window.API = API;
