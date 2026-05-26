/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },

  // ✅ REQUIRED FOR DEV MODE (fixes your error)
  allowedDevOrigins: [
    "http://localhost:3000",
    "http://172.23.96.1:3000",
  ],
};

export default nextConfig;
