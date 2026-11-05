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

interface MockVendor {
  id: string;
  vendorCode: string;
  legalName: string;
  displayName: string;
  category: string;
  vendorType: "COMPANY" | "INDIVIDUAL" | "AGENCY" | "CONTRACTOR";
  status: "ACTIVE" | "ONBOARDING" | "SUSPENDED" | "BLACKLISTED" | "OFFBOARDED";
  contactPerson: string;
  phone?: string;
  email?: string;
  services: string[];
}

const mockVendors: MockVendor[] = [
  {
    id: "vnd-1",
    vendorCode: "VND-2026-000001",
    legalName: "Apex Elevator Solutions Pvt Ltd",
    displayName: "Apex Lifts & Elevators",
    category: "Lift Maintenance & AMC",
    vendorType: "COMPANY",
    status: "ACTIVE",
    contactPerson: "Sundararajan M",
    phone: "+91 98400 12345",
    email: "service@apexelevators.com",
    services: ["Elevator Quarterly AMC", "Emergency Lift Trapped Recovery", "Annual Safety Audit"],
  },
  {
    id: "vnd-2",
    vendorCode: "VND-2026-000002",
    legalName: "GreenCare Landscape & Water Solutions",
    displayName: "GreenCare Landscaping",
    category: "Gardening & Landscape",
    vendorType: "AGENCY",
    status: "ACTIVE",
    contactPerson: "Priya V",
    phone: "+91 98400 67890",
    email: "contact@greencare.in",
    services: ["Lawn Mowing & Pruning", "Automatic Sprinkler Repair", "Organic Fertilizer Supply"],
  },
  {
    id: "vnd-3",
    vendorCode: "VND-2026-000003",
    legalName: "SuperClean Waste & Septic Management",
    displayName: "SuperClean Services",
    category: "Waste & STP Management",
    vendorType: "CONTRACTOR",
    status: "ONBOARDING",
    contactPerson: "Ramanan K",
    phone: "+91 98400 11122",
    services: ["STP Sludge Cleaning", "Septic Tank Pumping"],
  },
];

export default function VendorsPage() {
  const [viewMode, setViewMode] = useState<ViewMode>("standard");
  const [lang, setLang] = useState<Language>("en");
  const [selectedVendor, setSelectedVendor] = useState<MockVendor | null>(mockVendors[0]);
  const [legalName, setLegalName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [vendorType, setVendorType] = useState("COMPANY");

  const t = {
    en: {
      title: "Vendor & Service Provider Directory",
      subtitle: "Manage external society service providers, AMCs, contracts, and work order allocations.",
      easyMode: "Easy Directory",
      standardMode: "Standard Directory",
      adminMode: "Vendor Admin & Onboarding",
      addNew: "Add New Vendor Profile",
      legalNameLabel: "Legal Registered Name",
      displayNameLabel: "Display / Trade Name",
      vendorTypeLabel: "Vendor Entity Type",
      submitButton: "Register Vendor Profile",
      statusLabel: "Lifecycle Status",
      categoryLabel: "Primary Category",
      servicesHeading: "Offered Service Catalog",
      contactHeading: "Primary Representative Contact",
    },
    ta: {
      title: "விற்பனையாளர் மற்றும் சேவை வழங்குநர் அடைவு",
      subtitle: "வெளிப்புற சேவை வழங்குநர்கள், ஒப்பந்தங்கள் மற்றும் பணி ஆணை ஒதுக்கீடுகளை நிர்வகிக்கவும்.",
      easyMode: "எளிய பார்வை",
      standardMode: "நிலையான அடைவு",
      adminMode: "விற்பனையாளர் நிர்வாகம்",
      addNew: "புதிய விற்பனையாளரை சேர்க்கவும்",
      legalNameLabel: "சட்டபூர்வ பதிவு செய்த பெயர்",
      displayNameLabel: "வணிகப் பெயர்",
      vendorTypeLabel: "விற்பனையாளர் வகை",
      submitButton: "விற்பனையாளர் சுயவிவரத்தை பதிவு செய்",
      statusLabel: "நிலை",
      categoryLabel: "முதன்மை வகை",
      servicesHeading: "வழங்கப்படும் சேவைகள் பட்டியல்",
      contactHeading: "முதன்மை தொடர்பு நபர்",
    },
  }[lang];

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "ACTIVE":
        return <Badge variant="success">✅ ACTIVE (செயலில்)</Badge>;
      case "ONBOARDING":
        return <Badge variant="warning">⏳ ONBOARDING (சேர்ப்பு)</Badge>;
      case "SUSPENDED":
        return <Badge variant="error">⛔ SUSPENDED (இடைநிறுத்தம்)</Badge>;
      case "BLACKLISTED":
        return <Badge variant="error">🚫 BLACKLISTED (கருப்புப் பட்டியல்)</Badge>;
      case "OFFBOARDED":
        return <Badge variant="default">🔒 OFFBOARDED (விலகியவர்)</Badge>;
      default:
        return <Badge variant="default">{status}</Badge>;
    }
  };

  const vendorTypeOptions = [
    { value: "COMPANY", label: "Private Limited Company / Enterprise" },
    { value: "AGENCY", label: "Registered Service Agency" },
    { value: "CONTRACTOR", label: "Independent Contractor" },
    { value: "INDIVIDUAL", label: "Individual Freelancer" },
  ];

  return (
    <PageContainer title={t.title} subtitle={t.subtitle}>
      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6 pb-4 border-b">
        <div className="flex items-center gap-2">
          <Button
            variant={viewMode === "easy" ? "primary" : "outline"}
            onClick={() => setViewMode("easy")}
            className="min-h-[44px]"
          >
            🌱 {t.easyMode}
          </Button>
          <Button
            variant={viewMode === "standard" ? "primary" : "outline"}
            onClick={() => setViewMode("standard")}
            className="min-h-[44px]"
          >
            📊 {t.standardMode}
          </Button>
          <Button
            variant={viewMode === "admin" ? "primary" : "outline"}
            onClick={() => setViewMode("admin")}
            className="min-h-[44px]"
          >
            🛡️ {t.adminMode}
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant={lang === "en" ? "primary" : "outline"}
            size="sm"
            onClick={() => setLang("en")}
          >
            English
          </Button>
          <Button
            variant={lang === "ta" ? "primary" : "outline"}
            size="sm"
            onClick={() => setLang("ta")}
          >
            தமிழ்
          </Button>
        </div>
      </div>

      {/* EASY MODE */}
      {viewMode === "easy" && (
        <div className="space-y-6 max-w-2xl mx-auto">
          <Card>
            <CardHeader>
              <CardTitle>🏢 Society Approved Vendors & AMC Directory</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {mockVendors.map((vnd) => (
                <div
                  key={vnd.id}
                  className="p-4 border rounded-lg hover:bg-accent cursor-pointer flex flex-wrap items-center justify-between gap-2"
                  onClick={() => setSelectedVendor(vnd)}
                >
                  <div>
                    <div className="font-mono text-sm font-bold text-muted-foreground">
                      {vnd.vendorCode}
                    </div>
                    <div className="font-semibold text-lg">{vnd.displayName}</div>
                    <div className="text-sm text-muted-foreground">{vnd.category}</div>
                  </div>
                  <div>{getStatusBadge(vnd.status)}</div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {/* STANDARD & ADMIN DASHBOARD */}
      {viewMode !== "easy" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <div>
                  <CardTitle className="text-lg">{t.title}</CardTitle>
                  <p className="text-sm text-gray-500">
                    {viewMode === "admin"
                      ? "Vendor Onboarding & Status Governance"
                      : "Approved Vendor Directory"}
                  </p>
                </div>
                {viewMode === "admin" && <Button size="sm">➕ {t.addNew}</Button>}
              </CardHeader>
              <CardContent>
                <Table>
                  <thead>
                    <tr className="border-b text-left text-sm font-semibold text-muted-foreground">
                      <th className="py-2">Vendor Code</th>
                      <th className="py-2">Display Name</th>
                      <th className="py-2">Category</th>
                      <th className="py-2">Type</th>
                      <th className="py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mockVendors.map((vnd) => (
                      <tr
                        key={vnd.id}
                        className={`border-b cursor-pointer hover:bg-muted/50 ${
                          selectedVendor?.id === vnd.id ? "bg-muted font-medium" : ""
                        }`}
                        onClick={() => setSelectedVendor(vnd)}
                      >
                        <td className="py-3 font-mono text-xs">{vnd.vendorCode}</td>
                        <td className="py-3 font-medium">{vnd.displayName}</td>
                        <td className="py-3 text-sm">{vnd.category}</td>
                        <td className="py-3 text-xs">{vnd.vendorType}</td>
                        <td className="py-3">{getStatusBadge(vnd.status)}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </CardContent>
            </Card>

            {viewMode === "admin" && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">➕ {t.addNew}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-bold mb-1">{t.legalNameLabel}</label>
                      <Input
                        value={legalName}
                        onChange={(e) => setLegalName(e.target.value)}
                        placeholder="e.g. Apex Elevator Solutions Pvt Ltd"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-bold mb-1">{t.displayNameLabel}</label>
                      <Input
                        value={displayName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        placeholder="e.g. Apex Lifts & Elevators"
                      />
                    </div>
                  </div>

                  <div>
                    <Select
                      label={t.vendorTypeLabel}
                      options={vendorTypeOptions}
                      value={vendorType}
                      onChange={(e) => setVendorType(e.target.value)}
                    />
                  </div>

                  <Button
                    className="w-full"
                    onClick={() => {
                      alert("Vendor Profile Onboarded Successfully!");
                      setLegalName("");
                      setDisplayName("");
                    }}
                  >
                    {t.submitButton}
                  </Button>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Vendor Inspector */}
          <div>
            {selectedVendor ? (
              <Card className="sticky top-4">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-muted-foreground font-bold">
                      {selectedVendor.vendorCode}
                    </span>
                    {getStatusBadge(selectedVendor.status)}
                  </div>
                  <CardTitle className="text-xl mt-1">{selectedVendor.displayName}</CardTitle>
                  <p className="text-xs text-gray-500">{selectedVendor.legalName}</p>
                </CardHeader>

                <CardContent className="space-y-4">
                  <div className="text-sm space-y-2">
                    <div>
                      <span className="text-muted-foreground">{t.categoryLabel}:</span>{" "}
                      <span className="font-bold">{selectedVendor.category}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">{t.contactHeading}:</span>{" "}
                      <span>{selectedVendor.contactPerson}</span>
                    </div>
                  </div>

                  {selectedVendor.phone && (
                    <Alert title="Primary Contact Info" variant="info">
                      <div>
                        <strong>Phone:</strong> {selectedVendor.phone}
                      </div>
                      {selectedVendor.email && (
                        <div className="mt-1 text-xs">
                          <strong>Email:</strong> {selectedVendor.email}
                        </div>
                      )}
                    </Alert>
                  )}

                  <div>
                    <h4 className="text-sm font-bold mb-2">{t.servicesHeading}</h4>
                    <ul className="text-xs space-y-1 list-disc pl-4 text-muted-foreground">
                      {selectedVendor.services.map((svc, idx) => (
                        <li key={idx}>{svc}</li>
                      ))}
                    </ul>
                  </div>

                  {viewMode === "admin" && (
                    <div className="border-t pt-3 space-y-2">
                      <Button className="w-full" size="sm">
                        ✏️ Edit Vendor Profile
                      </Button>
                      <Button className="w-full" variant="outline" size="sm">
                        📄 Manage Compliance Documents
                      </Button>
                      <Button className="w-full" variant="danger" size="sm">
                        ⛔ Suspend / Blacklist
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="p-6 text-center text-muted-foreground">
                  Select a vendor profile to view details.
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </PageContainer>
  );
}
