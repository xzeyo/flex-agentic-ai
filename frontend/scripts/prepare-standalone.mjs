import { cp } from "node:fs/promises";

// Next's standalone server needs its static assets copied beside the server bundle.
await cp(".next/static", ".next/standalone/.next/static", { recursive: true });
