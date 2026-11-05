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

interface MockFacility {
  id: string;
  facilityCode: string;
  name: string;
  facilityType: string;
  status: "ACTIVE" | "UNDER_MAINTENANCE" | "TEMPORARILY_CLOSED" | "DECOMMISSIONED";
  capacity?: number;
  locationSummary?: string;
  isBookableSeparately: boolean;
  areasCount: number;
}

const mockFacilities: MockFacility[] = [
  {
    id: "fac-1",
    facilityCode: "FAC-2026-000001",
    name: "Grand Clubhouse",
    facilityType: "CLUBHOUSE",
    status: "ACTIVE",
    capacity: 250,
    locationSummary: "Central Plaza, Tower A West",
    isBookableSeparately: true,
    areasCount: 4,
  },
  {
    id: "fac-2",
    facilityCode: "FAC-2026-000002",
    name: "Olympic Swimming Pool",
    facilityType: "SWIMMING_POOL",
    status: "ACTIVE",
    capacity: 50,
    locationSummary: "North Lawn Complex",
    isBookableSeparately: false,
    areasCount: 2,
  },
  {
    id: "fac-3",
    facilityCode: "FAC-2026-000003",
    name: "Diesel Generator Room 1",
    facilityType: "POWER_BACKUP",
    status: "UNDER_MAINTENANCE",
    capacity: 0,
    locationSummary: "Basement B2, Block C",
    isBookableSeparately: false,
    areasCount: 1,
  },
];

export default function FacilitiesPage() {
  const [viewMode, setViewMode] = useState<ViewMode>("standard");
  const [lang, setLang] = useState<Language>("en");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const translations = {
    en: {
      title: "Society Facilities & Amenities",
      subtitle: "Manage society physical facilities, sub-areas, and operational statuses.",
      easyMode: "Simple View",
      standardMode: "Standard View",
      adminMode: "Admin View",
      searchPlaceholder: "Search by facility name or code...",
      allStatuses: "All Statuses",
      code: "Facility Code",
      name: "Name",
      type: "Facility Type",
      status: "Status",
      capacity: "Capacity",
      location: "Location",
      bookable: "Bookable",
      areas: "Sub-Areas",
    },
    ta: {
      title: "சமுதாய வசதிகள் மற்றும் வசதிகள்",
      subtitle: "சமுதாயத்தின் இயற்பியல் வசதிகள் மற்றும் துணை பகுதிகளை நிர்வகிக்கவும்.",
      easyMode: "எளிய பார்வை",
      standardMode: "நிலையான பார்வை",
      adminMode: "நிர்வாகி பார்வை",
      searchPlaceholder: "வசதி பெயர் அல்லது குறியீடு மூலம் தேடவும்...",
      allStatuses: "அனைத்து நிலைகளும்",
      code: "வசதி குறியீடு",
      name: "பெயர்",
      type: "வசதி வகை",
      status: "நிலை",
      capacity: "கொள்ளளவு",
      location: "இடம்",
      bookable: "முன்பதிவு செய்யக்கூடியது",
      areas: "துணை பகுதிகள்",
    },
  };

  const t = translations[lang];

  const filtered = mockFacilities.filter((f) => {
    const matchesSearch =
      f.name.toLowerCase().includes(search.toLowerCase()) ||
      f.facilityCode.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === "ALL" || f.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const getStatusBadge = (status: MockFacility["status"]) => {
    switch (status) {
      case "ACTIVE":
        return <Badge variant="success">Active</Badge>;
      case "UNDER_MAINTENANCE":
        return <Badge variant="warning">Maintenance</Badge>;
      case "TEMPORARILY_CLOSED":
        return <Badge variant="default">Closed</Badge>;
      case "DECOMMISSIONED":
        return <Badge variant="error">Decommissioned</Badge>;
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
          <CardTitle className="text-base font-semibold">Filter Facilities</CardTitle>
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
              { value: "ACTIVE", label: "Active" },
              { value: "UNDER_MAINTENANCE", label: "Maintenance" },
              { value: "TEMPORARILY_CLOSED", label: "Temporarily Closed" },
              { value: "DECOMMISSIONED", label: "Decommissioned" },
            ]}
            className="md:w-1/4"
          />
        </CardContent>
      </Card>

      {viewMode === "easy" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((fac) => (
            <Card key={fac.id} className="hover:shadow-md transition-shadow">
              <CardContent className="p-4">
                <div className="flex justify-between items-start mb-2">
                  <span className="text-xs font-mono font-medium text-gray-500">{fac.facilityCode}</span>
                  {getStatusBadge(fac.status)}
                </div>
                <h3 className="text-lg font-bold text-gray-900 mb-1">{fac.name}</h3>
                <p className="text-xs text-gray-500 mb-3">{fac.facilityType}</p>
                <div className="text-xs text-gray-600 space-y-1">
                  <p>
                    <strong>Location:</strong> {fac.locationSummary || "N/A"}
                  </p>
                  <p>
                    <strong>Capacity:</strong> {fac.capacity ? `${fac.capacity} persons` : "N/A"}
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
                  <th className="p-3">{t.type}</th>
                  <th className="p-3">{t.status}</th>
                  <th className="p-3">{t.capacity}</th>
                  <th className="p-3">{t.location}</th>
                  {viewMode === "admin" && <th className="p-3">{t.areas}</th>}
                </tr>
              </thead>
              <tbody className="divide-y text-sm">
                {filtered.map((fac) => (
                  <tr key={fac.id} className="hover:bg-gray-50">
                    <td className="p-3 font-mono font-medium text-xs text-gray-900">
                      {fac.facilityCode}
                    </td>
                    <td className="p-3 font-semibold text-gray-900">{fac.name}</td>
                    <td className="p-3 text-gray-600">{fac.facilityType}</td>
                    <td className="p-3">{getStatusBadge(fac.status)}</td>
                    <td className="p-3 text-gray-600">{fac.capacity || "N/A"}</td>
                    <td className="p-3 text-gray-600">{fac.locationSummary || "N/A"}</td>
                    {viewMode === "admin" && (
                      <td className="p-3 text-gray-600">{fac.areasCount} areas</td>
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
