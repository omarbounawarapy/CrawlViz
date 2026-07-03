# docs

- `crawl_messages.ts` — the WebSocket message contract pushed by
  `UIWebSocketGateway` (`ws://localhost:8765`) and consumed by the
  frontend's `state/eventNormalizer.js` / `state/reducer.js`. Written
  as TypeScript interfaces for precision; the frontend itself is
  plain JS, so this isn't compiled -- it's a reference for anyone
  touching either side of that boundary.
