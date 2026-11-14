import { gzipSync } from "node:zlib";
import type { Plugin } from "vite";

/** Count the full static JS graph, so moving bytes into a shared chunk cannot hide growth. */
export function performanceBudget(): Plugin {
  return {
    name: "fixrate-initial-js-budget",
    apply: "build",
    generateBundle(_options, bundle) {
      for (const entry of Object.values(bundle)) {
        if (entry.type !== "chunk" || !entry.isEntry) continue;
        const visited = new Set<string>();
        let bytes = 0;
        const visit = (name: string) => {
          const chunk = bundle[name];
          if (!chunk || chunk.type !== "chunk" || visited.has(name)) return;
          visited.add(name);
          bytes += gzipSync(chunk.code).length;
          chunk.imports.forEach(visit);
        };
        visit(entry.fileName);
        const limit = 150 * 1024;
        if (bytes > limit) this.error(`Initial JS is ${(bytes / 1024).toFixed(1)} KiB gzip; budget is 150 KiB. Split optional routes/features before increasing the budget.`);
      }
    },
  };
}
