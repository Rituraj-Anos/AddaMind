import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // The studio renders on the client from the API, so automatic instant-navigation validation only adds noise.
  experimental: { instantInsights: { validationLevel: "manual-warning" } },
  // Keep the dev-mode badge off the screen during live demos.
  devIndicators: false,
  turbopack: {
    // A stray package-lock.json in the home folder otherwise confuses root detection.
    root: __dirname,
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
