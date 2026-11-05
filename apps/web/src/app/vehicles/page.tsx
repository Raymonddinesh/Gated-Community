'use client';

import React, { useEffect, useState } from 'react';
import { PageContainer } from '@/components/ui/page-container';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { LoadingIndicator } from '@/components/ui/loading-indicator';
import { apiClient } from '@/lib/api-client';
import { authClient, UserMeResponse } from '@/lib/auth-client';

interface VehicleAssociation {
  id: string;
  unit_id: string;
  association_type: string;
  is_primary: boolean;
  status: string;
  unit_number?: string;
}

interface Vehicle {
  id: string;
  registration_number: string;
  normalized_registration_number: string;
  vehicle_type: string;
  make: string | null;
  model: string | null;
  variant: string | null;
  color: string | null;
  fuel_type: string;
  is_ev: boolean;
  battery_capacity_kwh: number | null;
  charging_required: boolean;
  status: string;
  verification_status: string;
  associations: VehicleAssociation[];
}

interface VehicleListResponse {
  items: Vehicle[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

interface AccessRecord {
  id: string;
  registration_number_snapshot: string;
  normalized_registration_number_snapshot: string;
  access_type: string;
  gate_identifier: string;
  access_time: string;
  detection_method: string;
  source_provider: string;
  notes: string | null;
}

interface AccessRecordListResponse {
  items: AccessRecord[];
  total: number;
}

export default function VehiclesPage() {
  const [activeMode, setActiveMode] = useState<'easy' | 'standard'>('easy');
  const [standardTab, setStandardTab] = useState<'my' | 'admin' | 'access' | 'register'>('my');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [myVehicles, setMyVehicles] = useState<Vehicle[]>([]);
  const [allVehicles, setAllVehicles] = useState<Vehicle[]>([]);
  const [accessRecords, setAccessRecords] = useState<AccessRecord[]>([]);

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [filterType, setFilterType] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<string>('');

  // Register Form State
  const [regPlate, setRegPlate] = useState<string>('');
  const [regType, setRegType] = useState<string>('FOUR_WHEELER');
  const [regMake, setRegMake] = useState<string>('');
  const [regModel, setRegModel] = useState<string>('');
  const [regColor, setRegColor] = useState<string>('');
  const [regFuel, setRegFuel] = useState<string>('PETROL');
  const [regIsEv, setRegIsEv] = useState<boolean>(false);
  const [regIsPrimary, setRegIsPrimary] = useState<boolean>(false);

  // Access Simulator State
  const [gatePlate, setGatePlate] = useState<string>('');
  const [gateType, setGateType] = useState<'ENTRY' | 'EXIT'>('ENTRY');
  const [gateId, setGateId] = useState<string>('GATE-MAIN-01');
  const [gateProvider, setGateProvider] = useState<string>('MANUAL');

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      // 1. Load my vehicles
      try {
        const myData = await apiClient<Vehicle[]>('/vehicles/me');
        setMyVehicles(myData);
      } catch {
        // Fallback if not authenticated or empty
        setMyVehicles([]);
      }

      // 2. Load all vehicles (if permitted)
      try {
        const allData = await apiClient<VehicleListResponse>('/vehicles?page=1&size=20');
        setAllVehicles(allData.items || []);
      } catch {
        setAllVehicles([]);
      }

      // 3. Load access records
      try {
        const accessData = await apiClient<AccessRecordListResponse>('/vehicles/access/records?page=1&size=20');
        setAccessRecords(accessData.items || []);
      } catch {
        setAccessRecords([]);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error loading vehicle information');
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);
    try {
      await apiClient('/vehicles', {
        method: 'POST',
        body: JSON.stringify({
          registration_number: regPlate,
          vehicle_type: regType,
          make: regMake || undefined,
          model: regModel || undefined,
          color: regColor || undefined,
          fuel_type: regIsEv ? 'ELECTRIC' : regFuel,
          is_ev: regIsEv,
          is_primary: regIsPrimary,
        }),
      });
      setSuccessMsg(`Vehicle ${regPlate.toUpperCase()} registered successfully!`);
      setRegPlate('');
      setRegMake('');
      setRegModel('');
      setRegColor('');
      setRegIsEv(false);
      setRegIsPrimary(false);
      await loadData();
      if (activeMode === 'standard') {
        setStandardTab('my');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    }
  }

  async function handleRecordGateEvent(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);
    try {
      await apiClient('/vehicles/access/records', {
        method: 'POST',
        body: JSON.stringify({
          registration_number: gatePlate,
          access_type: gateType,
          gate_identifier: gateId,
          source_provider: gateProvider,
          detection_method: gateProvider === 'MANUAL' ? 'MANUAL' : gateProvider.includes('RFID') ? 'RFID' : 'ANPR',
        }),
      });
      setSuccessMsg(`Gate ${gateType} event recorded for ${gatePlate.toUpperCase()}`);
      setGatePlate('');
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Gate record failed');
    }
  }

  async function handleVerify(vehicleId: string, status: 'VERIFIED' | 'REJECTED') {
    try {
      await apiClient(`/vehicles/${vehicleId}/verify`, {
        method: 'POST',
        body: JSON.stringify({
          verification_status: status,
          reason: `Admin approval: ${status}`,
        }),
      });
      setSuccessMsg(`Vehicle verification set to ${status}`);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Verification update failed');
    }
  }

  return (
    <PageContainer
      title="Vehicle Management & Access Foundation"
      subtitle="Phase 8: Multi-tenant vehicle registration, resident association, verification, and hardware gate access logs."
    >
      <div className="space-y-6">
        {/* Mode Selector and Controls */}
        <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm">
          <div>
            <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">Vehicle Management Console</h2>
            <p className="text-xs text-slate-500">Switch between Resident Easy Mode and Standard Operations Mode</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant={activeMode === 'easy' ? 'primary' : 'outline'}
              onClick={() => setActiveMode('easy')}
            >
              Easy Mode (Resident)
            </Button>
            <Button
              variant={activeMode === 'standard' ? 'primary' : 'outline'}
              onClick={() => setActiveMode('standard')}
            >
              Standard / Gate Mode
            </Button>
          </div>
        </div>

        {error && (
          <Alert variant="error" title="Notice">
            {error}
          </Alert>
        )}
        {successMsg && (
          <Alert variant="info" title="Success">
            {successMsg}
          </Alert>
        )}

        {/* ========================================================================= */}
        {/* EASY MODE — RESIDENT VIEW */}
        {/* ========================================================================= */}
        {activeMode === 'easy' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* My Registered Vehicles */}
              <div className="md:col-span-2 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">My Registered Vehicles</h3>
                  <Badge variant="info">{myVehicles.length} Registered</Badge>
                </div>

                {loading ? (
                  <LoadingIndicator label="Loading vehicles..." />
                ) : myVehicles.length === 0 ? (
                  <Card>
                    <CardContent className="p-8 text-center text-slate-500">
                      <p className="text-lg font-medium">No vehicles registered yet.</p>
                      <p className="text-sm mt-1">Use the quick registration form on the right to register your car or two-wheeler.</p>
                    </CardContent>
                  </Card>
                ) : (
                  <div className="grid grid-cols-1 gap-4">
                    {myVehicles.map((v) => {
                      const isPrimary = v.associations.some((a) => a.is_primary && a.status === 'ACTIVE');
                      return (
                        <Card key={v.id} className="border-l-4 border-l-blue-600">
                          <CardContent className="p-5">
                            <div className="flex flex-wrap items-start justify-between gap-2">
                              <div>
                                <div className="flex items-center gap-2">
                                  <span className="text-xl font-bold tracking-wider font-mono text-slate-900 dark:text-slate-100">
                                    {v.registration_number}
                                  </span>
                                  {isPrimary && (
                                    <Badge variant="success">Primary Vehicle</Badge>
                                  )}
                                  {v.is_ev && (
                                    <Badge variant="info">EV</Badge>
                                  )}
                                </div>
                                <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                                  {[v.make, v.model, v.variant].filter(Boolean).join(' ') || v.vehicle_type}
                                  {v.color && ` • Color: ${v.color}`}
                                </p>
                              </div>
                              <div className="text-right">
                                <Badge
                                  variant={
                                    v.verification_status === 'VERIFIED'
                                      ? 'success'
                                      : v.verification_status === 'PENDING'
                                      ? 'warning'
                                      : 'error'
                                  }
                                >
                                  {v.verification_status}
                                </Badge>
                                <p className="text-xs text-slate-400 mt-1">Status: {v.status}</p>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Quick Vehicle Registration (Easy Mode) */}
              <div>
                <Card>
                  <CardHeader>
                    <CardTitle>Register New Vehicle</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <form onSubmit={handleRegister} className="space-y-4 text-sm">
                      <div>
                        <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                          Registration Number *
                        </label>
                        <Input
                          placeholder="e.g. MH 02 AB 1234"
                          value={regPlate}
                          onChange={(e) => setRegPlate(e.target.value)}
                          required
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                            Type
                          </label>
                          <Select
                            value={regType}
                            onChange={(e) => setRegType(e.target.value)}
                            options={[
                              { value: 'FOUR_WHEELER', label: 'Car (4W)' },
                              { value: 'TWO_WHEELER', label: 'Bike/Scooter (2W)' },
                              { value: 'THREE_WHEELER', label: '3-Wheeler' },
                              { value: 'BICYCLE', label: 'Bicycle' },
                            ]}
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                            Fuel Type
                          </label>
                          <Select
                            value={regFuel}
                            onChange={(e) => setRegFuel(e.target.value)}
                            options={[
                              { value: 'PETROL', label: 'Petrol' },
                              { value: 'DIESEL', label: 'Diesel' },
                              { value: 'CNG', label: 'CNG' },
                              { value: 'ELECTRIC', label: 'Electric (EV)' },
                              { value: 'HYBRID', label: 'Hybrid' },
                            ]}
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                            Make
                          </label>
                          <Input
                            placeholder="e.g. Tata / Honda"
                            value={regMake}
                            onChange={(e) => setRegMake(e.target.value)}
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                            Model
                          </label>
                          <Input
                            placeholder="e.g. Nexon / Activa"
                            value={regModel}
                            onChange={(e) => setRegModel(e.target.value)}
                          />
                        </div>
                      </div>

                      <div className="flex items-center gap-4 pt-2">
                        <label className="flex items-center gap-2 cursor-pointer text-xs">
                          <input
                            type="checkbox"
                            checked={regIsEv}
                            onChange={(e) => setRegIsEv(e.target.checked)}
                            className="rounded border-slate-300"
                          />
                          <span>Electric Vehicle (EV)</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer text-xs">
                          <input
                            type="checkbox"
                            checked={regIsPrimary}
                            onChange={(e) => setRegIsPrimary(e.target.checked)}
                            className="rounded border-slate-300"
                          />
                          <span>Set Primary</span>
                        </label>
                      </div>

                      <Button type="submit" variant="primary" className="w-full mt-4">
                        Submit Vehicle Registration
                      </Button>
                    </form>
                  </CardContent>
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* STANDARD / ADMIN / GATE MODE */}
        {/* ========================================================================= */}
        {activeMode === 'standard' && (
          <div className="space-y-6">
            {/* Standard Mode Navigation Tabs */}
            <div className="flex border-b border-slate-200 dark:border-slate-800 text-sm">
              <button
                className={`px-4 py-2 border-b-2 font-medium ${
                  standardTab === 'my'
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
                onClick={() => setStandardTab('my')}
              >
                My Vehicles
              </button>
              <button
                className={`px-4 py-2 border-b-2 font-medium ${
                  standardTab === 'admin'
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
                onClick={() => setStandardTab('admin')}
              >
                All Society Vehicles (Admin Directory)
              </button>
              <button
                className={`px-4 py-2 border-b-2 font-medium ${
                  standardTab === 'access'
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
                onClick={() => setStandardTab('access')}
              >
                Gate Access Logs & Hardware Control
              </button>
            </div>

            {/* TAB: Admin Directory */}
            {standardTab === 'admin' && (
              <div className="space-y-4">
                <div className="flex flex-wrap gap-4 items-center justify-between">
                  <div className="flex items-center gap-2 max-w-sm">
                    <Input
                      placeholder="Search plate or model..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                    />
                  </div>
                  <Badge variant="default">{allVehicles.length} Total Vehicles</Badge>
                </div>

                <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
                  <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-800 text-sm text-left">
                    <thead className="bg-slate-50 dark:bg-slate-800 font-semibold text-slate-700 dark:text-slate-300">
                      <tr>
                        <th className="px-4 py-3">Registration Plate</th>
                        <th className="px-4 py-3">Vehicle Details</th>
                        <th className="px-4 py-3">Type / Fuel</th>
                        <th className="px-4 py-3">Status</th>
                        <th className="px-4 py-3">Verification</th>
                        <th className="px-4 py-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                      {allVehicles.map((v) => (
                        <tr key={v.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                          <td className="px-4 py-3 font-mono font-bold">{v.registration_number}</td>
                          <td className="px-4 py-3">
                            {[v.make, v.model].filter(Boolean).join(' ') || 'N/A'}
                            {v.color && <span className="text-xs text-slate-400"> ({v.color})</span>}
                          </td>
                          <td className="px-4 py-3">
                            {v.vehicle_type}
                            {v.is_ev ? (
                              <Badge variant="info" className="ml-1">EV</Badge>
                            ) : (
                              <span className="text-xs text-slate-500 ml-1">({v.fuel_type})</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <Badge variant={v.status === 'ACTIVE' ? 'success' : 'default'}>{v.status}</Badge>
                          </td>
                          <td className="px-4 py-3">
                            <Badge
                              variant={
                                v.verification_status === 'VERIFIED'
                                  ? 'success'
                                  : v.verification_status === 'PENDING'
                                  ? 'warning'
                                  : 'error'
                              }
                            >
                              {v.verification_status}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-right space-x-1">
                            {v.verification_status !== 'VERIFIED' && (
                              <Button
                                variant="outline"
                                onClick={() => handleVerify(v.id, 'VERIFIED')}
                              >
                                Approve
                              </Button>
                            )}
                            {v.verification_status !== 'REJECTED' && (
                              <Button
                                variant="outline"
                                onClick={() => handleVerify(v.id, 'REJECTED')}
                              >
                                Reject
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* TAB: Gate Access Logs */}
            {standardTab === 'access' && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Gate Logs Table */}
                <div className="md:col-span-2 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">Gate Access Event Log</h3>
                    <Badge variant="info">{accessRecords.length} Events</Badge>
                  </div>
                  <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
                    <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-800 text-sm text-left">
                      <thead className="bg-slate-50 dark:bg-slate-800 font-semibold text-slate-700 dark:text-slate-300">
                        <tr>
                          <th className="px-4 py-3">Time</th>
                          <th className="px-4 py-3">Plate</th>
                          <th className="px-4 py-3">Type</th>
                          <th className="px-4 py-3">Gate</th>
                          <th className="px-4 py-3">Method</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                        {accessRecords.map((r) => (
                          <tr key={r.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                            <td className="px-4 py-3 text-xs text-slate-500 font-mono">
                              {new Date(r.access_time).toLocaleTimeString()}
                            </td>
                            <td className="px-4 py-3 font-mono font-bold">
                              {r.registration_number_snapshot}
                            </td>
                            <td className="px-4 py-3">
                              <Badge variant={r.access_type === 'ENTRY' ? 'success' : 'default'}>
                                {r.access_type}
                              </Badge>
                            </td>
                            <td className="px-4 py-3 text-xs">{r.gate_identifier}</td>
                            <td className="px-4 py-3">
                              <Badge variant="info">{r.detection_method}</Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Gate Entry/Exit Simulator */}
                <div>
                  <Card>
                    <CardHeader>
                      <CardTitle>Record Gate Access Event</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <form onSubmit={handleRecordGateEvent} className="space-y-4 text-sm">
                        <div>
                          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                            Registration Number *
                          </label>
                          <Input
                            placeholder="e.g. MH 02 EV 1001"
                            value={gatePlate}
                            onChange={(e) => setGatePlate(e.target.value)}
                            required
                          />
                        </div>

                        <div>
                          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                            Movement Direction
                          </label>
                          <Select
                            value={gateType}
                            onChange={(e) => setGateType(e.target.value as 'ENTRY' | 'EXIT')}
                            options={[
                              { value: 'ENTRY', label: 'Gate Entry' },
                              { value: 'EXIT', label: 'Gate Exit' },
                            ]}
                          />
                        </div>

                        <div>
                          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                            Gate Identifier
                          </label>
                          <Input
                            placeholder="e.g. GATE-MAIN-01"
                            value={gateId}
                            onChange={(e) => setGateId(e.target.value)}
                          />
                        </div>

                        <div>
                          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                            Detection Hardware Provider
                          </label>
                          <Select
                            value={gateProvider}
                            onChange={(e) => setGateProvider(e.target.value)}
                            options={[
                              { value: 'MANUAL', label: 'Manual Security Guard' },
                              { value: 'RFID_STUB', label: 'RFID Reader (Tag simulation)' },
                              { value: 'ANPR_STUB', label: 'ANPR Camera (OCR simulation)' },
                            ]}
                          />
                        </div>

                        <Button type="submit" variant="primary" className="w-full mt-4">
                          Log Gate Event
                        </Button>
                      </form>
                    </CardContent>
                  </Card>
                </div>
              </div>
            )}

            {/* TAB: My Vehicles (Standard) */}
            {standardTab === 'my' && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {myVehicles.map((v) => (
                    <Card key={v.id}>
                      <CardContent className="p-4 space-y-2">
                        <div className="flex justify-between items-center">
                          <span className="font-mono font-bold text-lg">{v.registration_number}</span>
                          <Badge variant={v.verification_status === 'VERIFIED' ? 'success' : 'warning'}>
                            {v.verification_status}
                          </Badge>
                        </div>
                        <p className="text-sm text-slate-600 dark:text-slate-400">
                          {[v.make, v.model].filter(Boolean).join(' ') || v.vehicle_type}
                        </p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </PageContainer>
  );
}
