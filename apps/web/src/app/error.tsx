'use client';

import React, { useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/alert';

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // In production, send to error monitoring (Sentry / OpenTelemetry)
    console.error('Unhandled frontend application error:', error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
      <div className="max-w-md w-full bg-white p-8 rounded-2xl shadow-lg border border-gray-200">
        <h2 className="text-xl font-bold text-gray-900 mb-2">Something went wrong</h2>
        <Alert variant="error" className="mb-6">
          {error.message || 'An unexpected client error occurred.'}
        </Alert>
        <div className="flex justify-end gap-3">
          <Button variant="primary" onClick={() => reset()}>
            Try Again
          </Button>
        </div>
      </div>
    </div>
  );
}
