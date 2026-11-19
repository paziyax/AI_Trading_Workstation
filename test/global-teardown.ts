import { rmSync } from "node:fs";
import path from "node:path";

/** Remove the throwaway SQLite files created for this run. */
export default async function globalTeardown(): Promise<void> {
  rmSync(path.resolve(__dirname, ".tmp"), { recursive: true, force: true });
}
