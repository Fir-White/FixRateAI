import { gzipSync } from "node:zlib";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { Plugin } from "vite";

export function precompressAssets(): Plugin {
  return {
    name: "fixrate-precompress-assets",
    apply: "build",
    async writeBundle({ dir }, bundle) {
      if (!dir) return;
      const target = join(dir, "compressed");
      await mkdir(target, { recursive: true });
      for (const file of Object.values(bundle)) {
        const match = /^assets\/([^/]+-[\w-]{8}\.(?:js|css))$/.exec(file.fileName);
        if (!match) continue;
        // Vite resolves dynamic-import preload placeholders before writing.
        const source = await readFile(join(dir, file.fileName));
        if (source.length < 1024) continue;
        const gzip = gzipSync(source, { level: 9 });
        if (gzip.length < source.length) await writeFile(join(target, `${match[1]}.gz`), gzip);
      }
    },
  };
}

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
