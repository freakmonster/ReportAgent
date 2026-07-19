/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/session/:path*',
        destination: 'http://localhost:8010/session/:path*',
      },
    ];
  },
};

export default nextConfig;
