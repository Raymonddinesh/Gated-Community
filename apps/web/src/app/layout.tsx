import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'SocietySphere - Enterprise Apartment Society Management',
  description: 'Production-Grade Multi-Tenant Apartment Society Management Platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      </head>
      <body>{children}</body>
    </html>
  );
}
