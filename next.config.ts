import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  // The dev server only trusts the single LAN IP advertised by the opt-in launcher.
  ...(process.env.LAN_IP ? { allowedDevOrigins: [process.env.LAN_IP] } : {}),
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_ORIGIN || "http://127.0.0.1:8000"}/api/:path*`,
      },
    ];
  },
};
export default nextConfig;
