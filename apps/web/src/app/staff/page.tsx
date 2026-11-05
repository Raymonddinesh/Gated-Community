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

interface MockStaff {
  id: string;
  staffCode: string;
  name: string;
  role: string;
  engagement: "FULL_TIME" | "PART_TIME" | "CONTRACT";
  status: "ACTIVE" | "ONBOARDING" | "SUSPENDED" | "OFFBOARDED";
  joinedDate: string;
  phone?: string;
  emergencyContact?: string;
}

const mockStaffList: MockStaff[] = [
  {
    id: "stf-1",
    staffCode: "STF-2026-000001",
    name: "Karthik Subramanian",
    role: "Lead Electrician",
    engagement: "FULL_TIME",
    status: "ACTIVE",
    joinedDate: "2024-03-15",
    phone: "+91 98765 43210",
    emergencyContact: "Wife (Sita) +91 98765 00000",
  },
  {
    id: "stf-2",
    staffCode: "STF-2026-000002",
    name: "Ramesh Kumar",
    role: "Senior Plumber",
    engagement: "FULL_TIME",
    status: "ACTIVE",
    joinedDate: "2025-01-10",
    phone: "+91 98765 43211",
    emergencyContact: "Brother (Suresh) +91 98765 11111",
  },
  {
    id: "stf-3",
    staffCode: "STF-2026-000003",
    name: "Murugan P",
    role: "STP Plant Operator",
    engagement: "CONTRACT",
    status: "ONBOARDING",
    joinedDate: "2026-10-01",
  },
];

export default function StaffPage() {
  const [viewMode, setViewMode] = useState<ViewMode>("standard");
  const [lang, setLang] = useState<Language>("en");
  const [selectedStaff, setSelectedStaff] = useState<MockStaff | null>(mockStaffList[0]);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [role, setRole] = useState("ELECTRICIAN");
  const [phone, setPhone] = useState("");

  const t = {
    en: {
      title: "Staff & Workforce Directory",
      subtitle: "Manage internal society operational staff, roles, teams, and assignments.",
      easyMode: "Easy View",
      standardMode: "Standard Directory",
      adminMode: "Admin Workforce Control",
      addNew: "Add New Staff Member",
      firstName: "First Name",
      lastName: "Last Name",
      roleLabel: "Operational Role",
      phoneLabel: "Phone Number",
      submitButton: "Create Staff Profile",
      statusLabel: "Status",
      engagementLabel: "Engagement",
      joinedLabel: "Joined Date",
      emergencyLabel: "Emergency Contact (Sensitive)",
      rolesHeading: "Operational Roles & Teams",
    },
    ta: {
      title: "ஊழியர்கள் மற்றும் பணியாளர்கள் அடைவு",
      subtitle: "சமுதாய பணியாளர்கள், பாத்திரங்கள் மற்றும் அணிகளை நிர்வகிக்கவும்.",
      easyMode: "எளிய பார்வை",
      standardMode: "நிலையான அடைவு",
      adminMode: "நிர்வாகி கட்டுப்பாடு",
      addNew: "புதிய ஊழியரை சேர்க்கவும்",
      firstName: "முதல் பெயர்",
      lastName: "கடைசி பெயர்",
      roleLabel: "பணியாளர் பங்கு",
      phoneLabel: "தொலைபேசி எண்",
      submitButton: "ஊழியர் சுயவிவரத்தை உருவாக்கு",
      statusLabel: "நிலை",
      engagementLabel: "ஒப்பந்த வகை",
      joinedLabel: "சேர்ந்த தேதி",
      emergencyLabel: "அவசர தொடர்பு (ரகசிய தகவல்கள்)",
      rolesHeading: "செயல்பாட்டுப் பாத்திரங்கள் மற்றும் குழுக்கள்",
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
      case "OFFBOARDED":
        return <Badge variant="default">🔒 OFFBOARDED (விலகியவர்)</Badge>;
      default:
        return <Badge variant="default">{status}</Badge>;
    }
  };

  const roleOptions = [
    { value: "ELECTRICIAN", label: "Electrician (மின்சார பணியாளர்)" },
    { value: "PLUMBER", label: "Plumber (குழாய் சரிசெய்பவர்)" },
    { value: "STP_OPERATOR", label: "STP / WTP Operator (சுத்திகரிப்பு ஆலை)" },
    { value: "SECURITY_SUPERVISOR", label: "Security Supervisor (பாதுகாப்பு)" },
    { value: "HOUSEKEEPING", label: "Housekeeping Lead (தூய்மைப் பணி)" },
  ];

  return (
    <PageContainer title={t.title} subtitle={t.subtitle}>
      {/* View Mode & Language Selector Controls */}
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

      {/* EASY MODE UI */}
      {viewMode === "easy" && (
        <div className="space-y-6 max-w-2xl mx-auto">
          <Card>
            <CardHeader>
              <CardTitle>👷 Assigned Society Staff Directory</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {mockStaffList.map((stf) => (
                <div
                  key={stf.id}
                  className="p-4 border rounded-lg hover:bg-accent cursor-pointer flex flex-wrap items-center justify-between gap-2"
                  onClick={() => setSelectedStaff(stf)}
                >
                  <div>
                    <div className="font-mono text-sm font-bold text-muted-foreground">
                      {stf.staffCode}
                    </div>
                    <div className="font-semibold text-lg">{stf.name}</div>
                    <div className="text-sm text-muted-foreground">{stf.role}</div>
                  </div>
                  <div>{getStatusBadge(stf.status)}</div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {/* STANDARD & ADMIN DASHBOARD UI */}
      {viewMode !== "easy" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Staff Directory Table */}
          <div className="lg:col-span-2 space-y-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <div>
                  <CardTitle className="text-lg">{t.title}</CardTitle>
                  <p className="text-sm text-gray-500">
                    {viewMode === "admin"
                      ? "Workforce Administration & Status Control"
                      : "Operational Staff Directory"}
                  </p>
                </div>
                {viewMode === "admin" && <Button size="sm">➕ {t.addNew}</Button>}
              </CardHeader>
              <CardContent>
                <Table>
                  <thead>
                    <tr className="border-b text-left text-sm font-semibold text-muted-foreground">
                      <th className="py-2">Code</th>
                      <th className="py-2">Name</th>
                      <th className="py-2">Role</th>
                      <th className="py-2">Engagement</th>
                      <th className="py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mockStaffList.map((stf) => (
                      <tr
                        key={stf.id}
                        className={`border-b cursor-pointer hover:bg-muted/50 ${
                          selectedStaff?.id === stf.id ? "bg-muted font-medium" : ""
                        }`}
                        onClick={() => setSelectedStaff(stf)}
                      >
                        <td className="py-3 font-mono text-xs">{stf.staffCode}</td>
                        <td className="py-3 font-medium">{stf.name}</td>
                        <td className="py-3 text-sm">{stf.role}</td>
                        <td className="py-3 text-xs">{stf.engagement}</td>
                        <td className="py-3">{getStatusBadge(stf.status)}</td>
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
                      <label className="block text-sm font-bold mb-1">{t.firstName}</label>
                      <Input
                        value={firstName}
                        onChange={(e) => setFirstName(e.target.value)}
                        placeholder="e.g. Karthik"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-bold mb-1">{t.lastName}</label>
                      <Input
                        value={lastName}
                        onChange={(e) => setLastName(e.target.value)}
                        placeholder="e.g. Subramanian"
                      />
                    </div>
                  </div>

                  <div>
                    <Select
                      label={t.roleLabel}
                      options={roleOptions}
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-bold mb-1">{t.phoneLabel}</label>
                    <Input
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="+91 98765 43210"
                    />
                  </div>

                  <Button
                    className="w-full"
                    onClick={() => {
                      alert("Staff Profile Created Successfully!");
                      setFirstName("");
                      setLastName("");
                      setPhone("");
                    }}
                  >
                    {t.submitButton}
                  </Button>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Staff Detail & Privacy Inspector */}
          <div>
            {selectedStaff ? (
              <Card className="sticky top-4">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-muted-foreground font-bold">
                      {selectedStaff.staffCode}
                    </span>
                    {getStatusBadge(selectedStaff.status)}
                  </div>
                  <CardTitle className="text-xl mt-1">{selectedStaff.name}</CardTitle>
                  <p className="text-sm text-gray-500">{selectedStaff.role}</p>
                </CardHeader>

                <CardContent className="space-y-4">
                  <div className="text-sm space-y-2">
                    <div>
                      <span className="text-muted-foreground">{t.engagementLabel}:</span>{" "}
                      <span className="font-bold">{selectedStaff.engagement}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">{t.joinedLabel}:</span>{" "}
                      <span>{selectedStaff.joinedDate}</span>
                    </div>
                  </div>

                  {viewMode === "admin" && selectedStaff.phone && (
                    <Alert title="Sensitive Contact Information" variant="info">
                      <div>
                        <strong>Phone:</strong> {selectedStaff.phone}
                      </div>
                      {selectedStaff.emergencyContact && (
                        <div className="mt-1 text-xs text-muted-foreground">
                          <strong>Emergency:</strong> {selectedStaff.emergencyContact}
                        </div>
                      )}
                    </Alert>
                  )}

                  {viewMode !== "admin" && (
                    <p className="text-xs text-muted-foreground bg-gray-50 p-2 rounded">
                      🔒 Sensitive contact details masked for privacy.
                    </p>
                  )}

                  {viewMode === "admin" && (
                    <div className="border-t pt-3 space-y-2">
                      <Button className="w-full" size="sm">
                        ✏️ Edit Profile & Role
                      </Button>
                      <Button className="w-full" variant="outline" size="sm">
                        📄 Manage Documents
                      </Button>
                      <Button className="w-full" variant="danger" size="sm">
                        ⛔ Suspend / Offboard
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="p-6 text-center text-muted-foreground">
                  Select a staff member to inspect profile details.
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </PageContainer>
  );
}
