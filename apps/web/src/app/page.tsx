'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/navigation';
import { useRouter } from 'next/navigation';
import { PageContainer } from '@/components/ui/page-container';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { LoadingIndicator } from '@/components/ui/loading-indicator';
import { apiClient } from '@/lib/api-client';
import { authClient, UserMeResponse } from '@/lib/auth-client';

interface HealthResponse {
  status: string;
  app: string;
  environment: string;
  uptime_seconds: number;
}

export default function HomePage() {
  const router = useRouter();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [testInput, setTestInput] = useState<string>('');
  const [me, setMe] = useState<UserMeResponse | null>(null);
  const [authLoading, setAuthLoading] = useState<boolean>(false);

  useEffect(() => {
    async function fetchHealth() {
      try {
        setLoading(true);
        const data = await apiClient<HealthResponse>('/health');
        setHealth(data);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Unable to connect to backend API');
      } finally {
        setLoading(false);
      }
    }

    async function checkAuth() {
      const token = authClient.getAccessToken();
      if (!token) return;
      try {
        setAuthLoading(true);
        const meData = await authClient.getMe();
        setMe(meData);
      } catch {
        authClient.clearSession();
      } finally {
        setAuthLoading(false);
      }
    }

    fetchHealth();
    checkAuth();
  }, []);

  const handleLogout = async () => {
    await authClient.logout();
    setMe(null);
  };

  const handleSwitchSociety = async (societyId: string) => {
    try {
      await authClient.switchSociety(societyId);
      const updated = await authClient.getMe();
      setMe(updated);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to switch society');
    }
  };

  return (
    <PageContainer
      title="SocietySphere Enterprise Platform"
      subtitle="Phase 4: Double-Entry Financial Core & Accounting Provider Architecture"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* User Session & Authentication Card */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Authentication & Active Session</CardTitle>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => router.push('/finance')}>
                  Finance Console
                </Button>
                <Button variant="outline" size="sm" onClick={() => router.push('/billing')}>
                  Billing Console
                </Button>
                {me ? (
                  <Badge variant="success">Authenticated</Badge>
                ) : (
                  <Badge variant="default">Guest</Badge>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {authLoading ? (
              <LoadingIndicator label="Checking active session..." />
            ) : me ? (
              <div className="space-y-4 text-sm">
                <div>
                  <p className="font-semibold text-slate-800 dark:text-slate-100">{me.user.display_name}</p>
                  <p className="text-slate-500 font-mono text-xs">{me.user.email || me.user.phone}</p>
                </div>

                <div className="border-t border-slate-100 dark:border-slate-800 pt-3">
                  <p className="font-semibold text-xs text-slate-500 mb-1">ACTIVE ROLES & PERMISSIONS</p>
                  <div className="flex flex-wrap gap-1 mb-2">
                    {me.active_roles.map((r) => (
                      <Badge key={r} variant="default">{r}</Badge>
                    ))}
                  </div>
                  <p className="text-xs text-slate-400">
                    {me.active_permissions.length} granular permissions resolved
                  </p>
                </div>

                {me.memberships.length > 0 && (
                  <div className="border-t border-slate-100 dark:border-slate-800 pt-3">
                    <p className="font-semibold text-xs text-slate-500 mb-1">TENANT SOCIETIES</p>
                    <div className="space-y-2">
                      {me.memberships.map((s) => (
                        <div key={s.id} className="flex items-center justify-between text-xs">
                          <span>{s.display_name}</span>
                          {me.active_society_id === s.id ? (
                            <Badge variant="success">Active</Badge>
                          ) : (
                            <Button
                              variant="outline"
                              onClick={() => handleSwitchSociety(s.id)}
                            >
                              Switch
                            </Button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="pt-2 flex gap-2">
                  <Button variant="outline" onClick={handleLogout}>
                    Sign Out
                  </Button>
                  <Button
                    variant="outline"
                    onClick={async () => {
                      await authClient.logoutAll();
                      setMe(null);
                    }}
                  >
                    Sign Out All Devices
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-sm text-slate-600 dark:text-slate-400">
                  You are currently accessing the platform unauthenticated. Sign in to access your tenant dashboard and roles.
                </p>
                <Button variant="primary" onClick={() => router.push('/login')}>
                  Sign In to SocietySphere
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Backend Connectivity Status */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Backend Services Health</CardTitle>
              {health ? (
                <Badge variant="success">Online</Badge>
              ) : error ? (
                <Badge variant="error">Offline</Badge>
              ) : (
                <Badge variant="default">Checking</Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {loading && <LoadingIndicator label="Checking API status..." />}
            {error && (
              <Alert variant="warning" title="API Notice">
                Backend connection: {error}. (Ensure backend server is running on port 8000).
              </Alert>
            )}
            {health && (
              <div className="space-y-2 text-sm">
                <p><span className="font-semibold">Application:</span> {health.app}</p>
                <p><span className="font-semibold">Environment:</span> {health.environment}</p>
                <p><span className="font-semibold">Status:</span> {health.status}</p>
                <p><span className="font-semibold">Uptime:</span> {health.uptime_seconds}s</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Phase 6: Resident Payments, Receipts & Financial Reconciliation Card */}
        <Card className="md:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Resident Payments, Receipts & Financial Reconciliation</CardTitle>
              <Badge variant="success">Phase 6 Operational</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-sm">
              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                <p className="font-semibold text-slate-700 dark:text-slate-200">Payment Recording</p>
                <p className="text-xs text-slate-500 mt-1">
                  Offline/manual payment logging with payment methods (CASH, BANK, UPI, CHEQUE, DD), idempotency keys, and Bank/Cash GL postings.
                </p>
                <div className="mt-2">
                  <Badge variant="success">Auto & FIFO Allocation</Badge>
                </div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                <p className="font-semibold text-slate-700 dark:text-slate-200">Receipt Management</p>
                <p className="text-xs text-slate-500 mt-1">
                  Unique sequential numbering per society (REC-000001). Immutability guaranteed; cancellation supported with full audit trail.
                </p>
                <div className="mt-2">
                  <Badge variant="success">Immutable Receipts</Badge>
                </div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                <p className="font-semibold text-slate-700 dark:text-slate-200">Bank Reconciliation</p>
                <p className="text-xs text-slate-500 mt-1">
                  Reconciliation sessions, statement item matching, discrepancy tracking, and period closure controls.
                </p>
                <div className="mt-2">
                  <Badge variant="success">Statement Matching</Badge>
                </div>
              </div>
              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                <p className="font-semibold text-slate-700 dark:text-slate-200">Payment Reversal</p>
                <p className="text-xs text-slate-500 mt-1">
                  Controlled payment reversal unwinds invoice allocations, voids receipts, and generates balanced mirror GL reversal journals.
                </p>
                <div className="mt-2">
                  <Badge variant="success">Audited Reversals</Badge>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Phase 7: Resident, Owner, Tenant & Occupancy Management Card */}
        <Card className="md:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Resident, Owner, Tenant & Occupancy Management</CardTitle>
                <p className="text-xs text-slate-500 mt-1">
                  Authoritative multi-tenant ownership, occupancy lifecycle, household relations, and privacy-preserving self-service.
                </p>
              </div>
              <Badge variant="success">Phase 7 Operational</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-sm">
              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-slate-700 dark:text-slate-200">Unit Ownership</p>
                  <Badge variant="info">Max 100%</Badge>
                </div>
                <p className="text-xs text-slate-500 mt-2">
                  Single and joint co-ownership with strict validation (total &le; 100%). Full audit preservation on ownership transfers.
                </p>
                <ul className="text-xs text-slate-600 dark:text-slate-400 mt-2 space-y-1">
                  <li>&bull; Undivided share tracking</li>
                  <li>&bull; Joint ownership support</li>
                  <li>&bull; Non-destructive transfer</li>
                </ul>
              </div>

              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-slate-700 dark:text-slate-200">Occupancy Lifecycle</p>
                  <Badge variant="info">No Overlap</Badge>
                </div>
                <p className="text-xs text-slate-500 mt-2">
                  Controlled move-in & move-out. Strict temporal overlap prevention for rental leases with physical unit status synchronization.
                </p>
                <ul className="text-xs text-slate-600 dark:text-slate-400 mt-2 space-y-1">
                  <li>&bull; Move-in / Move-out workflows</li>
                  <li>&bull; Conflict rejection (HTTP 409)</li>
                  <li>&bull; Complete tenancy history</li>
                </ul>
              </div>

              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-slate-700 dark:text-slate-200">Household & Delegates</p>
                  <Badge variant="info">Scoped</Badge>
                </div>
                <p className="text-xs text-slate-500 mt-2">
                  Family members with designated access scopes and authorized delegates with revocable permissions and validity periods.
                </p>
                <ul className="text-xs text-slate-600 dark:text-slate-400 mt-2 space-y-1">
                  <li>&bull; Spouse, Child, Parent linking</li>
                  <li>&bull; Time-bound delegate grants</li>
                  <li>&bull; Instant delegate revocation</li>
                </ul>
              </div>

              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-slate-700 dark:text-slate-200">Self-Service & Privacy</p>
                  <Badge variant="success">Easy Mode</Badge>
                </div>
                <p className="text-xs text-slate-500 mt-2">
                  Deterministic profile completeness, emergency contact management, and privacy masking across tenant directories.
                </p>
                <ul className="text-xs text-slate-600 dark:text-slate-400 mt-2 space-y-1">
                  <li>&bull; My Profile / My Home APIs</li>
                  <li>&bull; Phone & email masking</li>
                  <li>&bull; Senior-friendly accessibility</li>
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Phase 8: Vehicle Management & Vehicle Access Foundation Card */}
        <Card className="md:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Vehicle Management & Access Control Foundation</CardTitle>
                <p className="text-xs text-slate-500 mt-1">
                  Multi-tenant vehicle registry, resident unit linkage, verification workflows, and hardware gate event audit logs.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="success">Phase 8 Operational</Badge>
                <Button variant="primary" onClick={() => router.push('/vehicles')}>
                  Open Vehicle Console
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-sm">
              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-slate-700 dark:text-slate-200">Plate Normalization</p>
                  <Badge variant="info">Unique Active</Badge>
                </div>
                <p className="text-xs text-slate-500 mt-2">
                  Deterministic plate normalization (uppercase alphanumeric) preventing duplicate active registrations within a society.
                </p>
                <ul className="text-xs text-slate-600 dark:text-slate-400 mt-2 space-y-1">
                  <li>&bull; Auto-formatting & strip</li>
                  <li>&bull; Concurrency lock guard</li>
                  <li>&bull; 4W, 2W, 3W, Bicycle</li>
                </ul>
              </div>

              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-slate-700 dark:text-slate-200">Resident Association</p>
                  <Badge variant="info">Primary Slot</Badge>
                </div>
                <p className="text-xs text-slate-500 mt-2">
                  Decoupled authorization linking vehicles to owners, tenants, and units with primary vehicle designation per resident/unit.
                </p>
                <ul className="text-xs text-slate-600 dark:text-slate-400 mt-2 space-y-1">
                  <li>&bull; Owner & Tenant vehicles</li>
                  <li>&bull; Multi-vehicle household</li>
                  <li>&bull; Auto-demote old primary</li>
                </ul>
              </div>

              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-slate-700 dark:text-slate-200">Verification & Docs</p>
                  <Badge variant="info">Audit Trail</Badge>
                </div>
                <p className="text-xs text-slate-500 mt-2">
                  Structured vehicle document repository (RC, insurance, PUC) and audited management/security verification workflows.
                </p>
                <ul className="text-xs text-slate-600 dark:text-slate-400 mt-2 space-y-1">
                  <li>&bull; RC / Insurance records</li>
                  <li>&bull; Approve / Reject actions</li>
                  <li>&bull; Full verification log</li>
                </ul>
              </div>

              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-slate-700 dark:text-slate-200">Gate Access & Hardware</p>
                  <Badge variant="success">RFID / ANPR</Badge>
                </div>
                <p className="text-xs text-slate-500 mt-2">
                  Append-only immutable gate access records with provider abstraction ready for manual guard entry, RFID, and ANPR cameras.
                </p>
                <ul className="text-xs text-slate-600 dark:text-slate-400 mt-2 space-y-1">
                  <li>&bull; Entry / Exit timestamps</li>
                  <li>&bull; Provider abstraction stub</li>
                  <li>&bull; Immutable access log</li>
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
