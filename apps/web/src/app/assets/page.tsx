"use client";

import React, { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageContainer } from "@/components/ui/page-container";
import { Select } from "@/components/ui/select";
import { Table } from "@/components/ui/table";

type ViewMode = "easy" | "standard" | "admin";
type Language = "en" | "ta";

interface MockAsset {
  id: string;
  assetCode: string;
  name: string;
  category: string;
  status: "IN_SERVICE" | "UNDER_MAINTENANCE" | "OUT_OF_SERVICE" | "DECOMMISSIONED" | "DISPOSED";
  criticality: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  serialNumber?: string;
  modelNumber?: string;
  facilityName?: string;
  vendorName?: string;
}

const mockAssets: MockAsset[] = [
  {
    id: "ast-1",
    assetCode: "AST-2026-000001",
    name: "500 KVA Diesel Generator 1",
    category: "Power Infrastructure",
    status: "IN_SERVICE",
    criticality: "CRITICAL",
    serialNumber: "DG-500-89123",
    modelNumber: "Kirloskar KG-500",
    facilityName: "Diesel Generator Room 1",
    vendorName: "Kirloskar Electric Ltd",
  },
  {
    id: "ast-2",
    assetCode: "AST-2026-000002",
    name: "Passenger Elevator Motor A",
    category: "Elevator & Vertical Transport",
    status: "UNDER_MAINTENANCE",
    criticality: "HIGH",
    serialNumber: "EM-2024-551",
    modelNumber: "Schindler 3300",
    facilityName: "Grand Clubhouse",
    vendorName: "Apex Lifts & Elevators",
  },
  {
    id: "ast-3",
    assetCode: "AST-2026-000003",
    name: "Commercial Treadmill 2",
    category: "Gym Equipment",
    status: "IN_SERVICE",
    criticality: "LOW",
    serialNumber: "TM-LIFE-901",
    modelNumber: "LifeFitness T5",
    facilityName: "Grand Clubhouse",
    vendorName: "Fitness World Pvt Ltd",
  },
];

export default function AssetsPage() {
  const [viewMode, setViewMode] = useState<ViewMode>("standard");
  const [lang, setLang] = useState<Language>("en");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const translations = {
    en: {
      title: "Society Asset Register",
      subtitle: "Track physical equipment, machinery, serial numbers, and maintenance status.",
      easyMode: "Simple View",
      standardMode: "Standard View",
      adminMode: "Admin View",
      searchPlaceholder: "Search by asset name, code, or serial...",
      allStatuses: "All Statuses",
      code: "Asset Code",
      name: "Name",
      category: "Category",
      status: "Status",
      criticality: "Criticality",
      serial: "Serial Number",
      facility: "Facility",
    },
    ta: {
      title: "சமுதாய சொத்துக்கள் பதிவேடு",
      subtitle: "இயற்பியல் உபகரணங்கள், இயந்திரங்கள், வரிசை எண்கள் மற்றும் பராமரிப்பு நிலையை கண்காணிக்கவும்.",
      easyMode: "எளிய பார்வை",
      standardMode: "நிலையான பார்வை",
      adminMode: "நிர்வாகி பார்வை",
      searchPlaceholder: "சொத்து பெயர், குறியீடு அல்லது வரிசை எண் மூலம் தேடவும்...",
      allStatuses: "அனைத்து நிலைகளும்",
      code: "சொத்து குறியீடு",
      name: "பெயர்",
      category: "பிரிவு",
      status: "நிலை",
      criticality: "முக்கியத்துவம்",
      serial: "வரிசை எண்",
      facility: "வசதி",
    },
  };

  const t = translations[lang];

  const filtered = mockAssets.filter((a) => {
    const matchesSearch =
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.assetCode.toLowerCase().includes(search.toLowerCase()) ||
      (a.serialNumber && a.serialNumber.toLowerCase().includes(search.toLowerCase()));
    const matchesStatus = statusFilter === "ALL" || a.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const getStatusBadge = (status: MockAsset["status"]) => {
    switch (status) {
      case "IN_SERVICE":
        return <Badge variant="success">In Service</Badge>;
      case "UNDER_MAINTENANCE":
        return <Badge variant="warning">Maintenance</Badge>;
      case "OUT_OF_SERVICE":
        return <Badge variant="error">Out of Service</Badge>;
      case "DECOMMISSIONED":
      case "DISPOSED":
        return <Badge variant="default">{status}</Badge>;
    }
  };

  const getCriticalityBadge = (crit: MockAsset["criticality"]) => {
    switch (crit) {
      case "CRITICAL":
        return <Badge variant="error">Critical</Badge>;
      case "HIGH":
        return <Badge variant="warning">High</Badge>;
      case "MEDIUM":
        return <Badge variant="info">Medium</Badge>;
      case "LOW":
        return <Badge variant="default">Low</Badge>;
    }
  };

  return (
    <PageContainer>
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t.title}</h1>
          <p className="text-sm text-gray-600">{t.subtitle}</p>
        </div>

        <div className="flex items-center gap-2">
          {/* Language Toggle */}
          <div className="flex border rounded-md overflow-hidden bg-white text-xs">
            <button
              onClick={() => setLang("en")}
              className={`px-3 py-1.5 font-medium ${
                lang === "en" ? "bg-primary text-white" : "text-gray-600 hover:bg-gray-100"
              }`}
            >
              English
            </button>
            <button
              onClick={() => setLang("ta")}
              className={`px-3 py-1.5 font-medium ${
                lang === "ta" ? "bg-primary text-white" : "text-gray-600 hover:bg-gray-100"
              }`}
            >
              தமிழ்
            </button>
          </div>

          {/* View Mode Toggle */}
          <div className="flex border rounded-md overflow-hidden bg-white text-xs">
            <button
              onClick={() => setViewMode("easy")}
              className={`px-3 py-1.5 font-medium ${
                viewMode === "easy" ? "bg-primary text-white" : "text-gray-600 hover:bg-gray-100"
              }`}
            >
              {t.easyMode}
            </button>
            <button
              onClick={() => setViewMode("standard")}
              className={`px-3 py-1.5 font-medium ${
                viewMode === "standard" ? "bg-primary text-white" : "text-gray-600 hover:bg-gray-100"
              }`}
            >
              {t.standardMode}
            </button>
            <button
              onClick={() => setViewMode("admin")}
              className={`px-3 py-1.5 font-medium ${
                viewMode === "admin" ? "bg-primary text-white" : "text-gray-600 hover:bg-gray-100"
              }`}
            >
              {t.adminMode}
            </button>
          </div>
        </div>
      </div>

      <Card className="mb-6">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">Filter Assets</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col md:flex-row gap-4">
          <Input
            placeholder={t.searchPlaceholder}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="md:w-1/3"
          />
          <Select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            options={[
              { value: "ALL", label: t.allStatuses },
              { value: "IN_SERVICE", label: "In Service" },
              { value: "UNDER_MAINTENANCE", label: "Maintenance" },
              { value: "OUT_OF_SERVICE", label: "Out of Service" },
              { value: "DECOMMISSIONED", label: "Decommissioned" },
              { value: "DISPOSED", label: "Disposed" },
            ]}
            className="md:w-1/4"
          />
        </CardContent>
      </Card>

      {viewMode === "easy" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((asset) => (
            <Card key={asset.id} className="hover:shadow-md transition-shadow">
              <CardContent className="p-4">
                <div className="flex justify-between items-start mb-2">
                  <span className="text-xs font-mono font-medium text-gray-500">{asset.assetCode}</span>
                  {getStatusBadge(asset.status)}
                </div>
                <h3 className="text-lg font-bold text-gray-900 mb-1">{asset.name}</h3>
                <p className="text-xs text-gray-500 mb-3">{asset.category}</p>
                <div className="text-xs text-gray-600 space-y-1">
                  <p>
                    <strong>Facility:</strong> {asset.facilityName || "Unassigned"}
                  </p>
                  <p>
                    <strong>Criticality:</strong> {getCriticalityBadge(asset.criticality)}
                  </p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <thead>
                <tr className="border-b bg-gray-50 text-left text-xs font-semibold text-gray-600">
                  <th className="p-3">{t.code}</th>
                  <th className="p-3">{t.name}</th>
                  <th className="p-3">{t.category}</th>
                  <th className="p-3">{t.status}</th>
                  <th className="p-3">{t.criticality}</th>
                  <th className="p-3">{t.facility}</th>
                  {viewMode === "admin" && <th className="p-3">{t.serial}</th>}
                </tr>
              </thead>
              <tbody className="divide-y text-sm">
                {filtered.map((asset) => (
                  <tr key={asset.id} className="hover:bg-gray-50">
                    <td className="p-3 font-mono font-medium text-xs text-gray-900">
                      {asset.assetCode}
                    </td>
                    <td className="p-3 font-semibold text-gray-900">{asset.name}</td>
                    <td className="p-3 text-gray-600">{asset.category}</td>
                    <td className="p-3">{getStatusBadge(asset.status)}</td>
                    <td className="p-3">{getCriticalityBadge(asset.criticality)}</td>
                    <td className="p-3 text-gray-600">{asset.facilityName || "Unassigned"}</td>
                    {viewMode === "admin" && (
                      <td className="p-3 font-mono text-xs text-gray-600">
                        {asset.serialNumber || "N/A"}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardContent>
        </Card>
      )}
    </PageContainer>
  );
}
