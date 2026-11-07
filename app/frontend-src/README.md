# Apollo frontend

React 19, TypeScript, Vite, and Tailwind CSS. Use Node.js 24 LTS.

From this directory:

```bash
npm ci
npm run dev    # API must run on localhost:8000; /api and WebSockets are proxied
npm run lint
npm run build  # typecheck and emit ../frontend_dist for FastAPI
```

The UI offers three synthetic case dossiers with Summary, Diagnostics, Ask, and Documents tabs. Demo documents are read-only. Ask streams an answer followed by evaluation and suggested follow-up questions; closing the tab cancels its socket. Uploaded patient namespaces are currently an API-only workflow.

The [root README](../../README.md) documents backend setup, optional model dependencies, environment variables, API contracts, tests, and limitations. Do not commit `node_modules`, `*.tsbuildinfo`, or generated `frontend_dist` assets.
