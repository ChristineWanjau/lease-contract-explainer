import type { NextConfig } from "next";

// GitHub Pages: STATIC_EXPORT=1 builds plain HTML into out/, served from
// https://<user>.github.io/<repo>/, so assets need the repo name as a prefix.
const staticExport = process.env.STATIC_EXPORT === "1";
const basePath = process.env.BASE_PATH ?? "";

const nextConfig: NextConfig = {
  ...(staticExport && { output: "export", basePath, trailingSlash: true }),
  // Partial prerendering can't run in export mode, so it's on for the normal
  // build only. The page is a client component, so the export doesn't lose anything.
  cacheComponents: !staticExport,
  partialPrefetching: !staticExport,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
