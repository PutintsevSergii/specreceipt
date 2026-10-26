/** Ordered product configuration migrations, independent of CLI presentation. */
import { config } from "./core.js";
export const CONFIG_VERSION = 2;
export function migrate(input: unknown): {
  value: Record<string, unknown>;
  applied: string[];
} {
  config(input);
  const value = { ...(input as Record<string, unknown>) };
  const applied: string[] = [];
  if (value.schemaVersion === 1) {
    value.schemaVersion = 2;
    value.engine = { protocolVersion: 1 };
    applied.push("product-1-to-2");
  }
  config(value);
  return { value, applied };
}
