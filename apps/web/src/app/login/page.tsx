'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { PageContainer } from '@/components/ui/page-container';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert } from '@/components/ui/alert';
import { authClient } from '@/lib/auth-client';
import { ApiClientError } from '@/lib/api-client';

export default function LoginPage() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await authClient.login(identifier, password);
      router.push('/');
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setError(err.message || 'Invalid username or password.');
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred during login.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageContainer
      title="SocietySphere Access Portal"
      subtitle="Multi-Tenant Society Authentication & Session Management"
    >
      <div className="max-w-md mx-auto pt-8">
        <Card>
          <CardHeader>
            <CardTitle>Sign In</CardTitle>
          </CardHeader>
          <CardContent>
            {error && (
              <div className="mb-4">
                <Alert variant="error" title="Authentication Failed">
                  {error}
                </Alert>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label
                  htmlFor="identifier"
                  className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1"
                >
                  Email Address or Mobile Phone
                </label>
                <Input
                  id="identifier"
                  type="text"
                  placeholder="e.g. superadmin@societysphere.io or +919876543210"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  required
                  disabled={loading}
                  autoComplete="username"
                />
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1"
                >
                  Password
                </label>
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={loading}
                  autoComplete="current-password"
                />
              </div>

              <div className="pt-2">
                <Button
                  type="submit"
                  variant="primary"
                  className="w-full"
                  disabled={loading || !identifier.trim() || !password}
                >
                  {loading ? 'Authenticating...' : 'Sign In'}
                </Button>
              </div>
            </form>

            <div className="mt-6 border-t border-slate-200 dark:border-slate-800 pt-4 text-xs text-slate-500">
              <p className="font-semibold mb-1">Testing Credentials:</p>
              <ul className="space-y-1 font-mono">
                <li>superadmin@societysphere.io / Password123!</li>
                <li>owner.a@palmstree.in / Password123!</li>
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
