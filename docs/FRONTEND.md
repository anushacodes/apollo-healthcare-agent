# Apollo frontend

React 19, TypeScript, Vite, and Tailwind CSS. Use Node.js 24 LTS.

From the repository root:

```bash
npm --prefix app/frontend-src install
npm --prefix app/frontend-src run dev    # API must run on localhost:8000; /api and WebSockets are proxied
npm --prefix app/frontend-src run lint
npm --prefix app/frontend-src run build  # typecheck and emit app/frontend_dist for FastAPI
```

The UI offers three synthetic case dossiers with Overview, Analysis, Ask, and Documents tabs. Existing source documents are read-only; users can upload or paste additional documents and review extracted fields. Ask streams workflow events and delivers an answer followed by evaluation and suggested follow-up questions; closing the tab cancels its socket. Creating a separate uploaded patient namespace is currently an API-only workflow.

The [root README](../README.md) documents backend setup, optional model dependencies, environment variables, API contracts, tests, and limitations. Do not commit `node_modules`, `*.tsbuildinfo`, or generated `frontend_dist` assets.
