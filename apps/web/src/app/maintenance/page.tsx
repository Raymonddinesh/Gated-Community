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

interface MockWorkOrder {
  id: string;
  number: string;
  title: string;
  category: string;
  priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  status: "OPEN" | "ASSIGNED" | "SCHEDULED" | "IN_PROGRESS" | "COMPLETED" | "VERIFIED" | "CLOSED";
  scheduledStart?: string;
  assignedTo?: string;
  createdAt: string;
}

const mockWorkOrders: MockWorkOrder[] = [
  {
    id: "wo-1",
    number: "WO-2026-000001",
    title: "STP Pump Vibration Check",
    category: "STP / WTP",
    priority: "HIGH",
    status: "IN_PROGRESS",
    scheduledStart: "2026-10-05 10:00 AM",
    assignedTo: "Karthik (Internal Staff)",
    createdAt: "2026-10-04",
  },
  {
    id: "wo-2",
    number: "WO-2026-000002",
    title: "Block B Lift 2 Door Sensor Repair",
    category: "Lift",
    priority: "CRITICAL",
    status: "ASSIGNED",
    scheduledStart: "2026-10-04 04:00 PM",
    assignedTo: "Elevator Tech Lead",
    createdAt: "2026-10-04",
  },
  {
    id: "wo-3",
    number: "WO-2026-000003",
    title: "Clubhouse Solar Inverter Routine Check",
    category: "Solar",
    priority: "LOW",
    status: "OPEN",
    createdAt: "2026-10-03",
  },
];

export default function MaintenancePage() {
  const [viewMode, setViewMode] = useState<ViewMode>("standard");
  const [lang, setLang] = useState<Language>("en");
  const [selectedOrder, setSelectedOrder] = useState<MockWorkOrder | null>(mockWorkOrders[0]);
  const [newTitle, setNewTitle] = useState("");
  const [newCategory, setNewCategory] = useState("Plumbing");

  const t = {
    en: {
      title: "Maintenance & Work Order Management",
      subtitle: "Track, schedule, assign, and resolve facility work orders cleanly.",
      easyMode: "Easy Mode (Resident)",
      standardMode: "Standard Mode",
      adminMode: "Admin Dashboard",
      myWorkOrders: "My Work Orders",
      createNew: "Report Maintenance Issue",
      issueTitle: "What needs fixing?",
      categoryLabel: "Category",
      submitButton: "Submit Work Order",
      statusLabel: "Status",
      priorityLabel: "Priority",
      scheduleLabel: "Scheduled Time",
      assignedTo: "Assigned To",
      materials: "Material Usage Tracking (Operational)",
      timeline: "Activity Timeline",
      verifyButton: "Verify & Accept Resolution",
    },
    ta: {
      title: "பராமரிப்பு மற்றும் பணி ஆணை நிர்வாகம்",
      subtitle: "சமுதாய பராமரிப்பு பணிகளை கண்காணிக்கவும் மற்றும் நிர்வகிக்கவும்.",
      easyMode: "எளிய முறை (குடியிருப்பாளர்)",
      standardMode: "நிலையான முறை",
      adminMode: "நிர்வாகி டாஷ்போர்டு",
      myWorkOrders: "எனது பராமரிப்பு கோரிக்கைகள்",
      createNew: "புதிய பராமரிப்பு பிரச்சனை",
      issueTitle: "என்ன சரிசெய்யப்பட வேண்டும்?",
      categoryLabel: "பிரிவு",
      submitButton: "பணி ஆணை சமர்ப்பி",
      statusLabel: "நிலை",
      priorityLabel: "முன்னுரிமை",
      scheduleLabel: "திட்டமிடப்பட்ட நேரம்",
      assignedTo: "ஒதுக்கப்பட்டவர்",
      materials: "பொருட்கள் பயன்பாடு",
      timeline: "செயல்பாட்டு வரலாறு",
      verifyButton: "தீர்வை சரிபார் & ஏற்றுக்கொள்",
    },
  }[lang];

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "IN_PROGRESS":
        return <Badge variant="warning">⏳ IN_PROGRESS (செயலில்)</Badge>;
      case "ASSIGNED":
        return <Badge variant="info">👤 ASSIGNED (ஒதுக்கப்பட்டது)</Badge>;
      case "COMPLETED":
        return <Badge variant="success">✅ COMPLETED (முடிந்தது)</Badge>;
      case "VERIFIED":
        return <Badge variant="success">✨ VERIFIED (சரிபார்க்கப்பட்டது)</Badge>;
      default:
        return <Badge variant="default">📋 {status}</Badge>;
    }
  };

  const categoryOptions = [
    { value: "Plumbing", label: "Plumbing (குழாய்/நீர்)" },
    { value: "Electrical", label: "Electrical (மின்சாரம்)" },
    { value: "Lift", label: "Lift (மின் தூக்கி)" },
    { value: "Common Area", label: "Common Area (பொது இடம்)" },
  ];

  return (
    <PageContainer title={t.title} subtitle={t.subtitle}>
      {/* Top View Mode & Language Selector Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6 pb-4 border-b">
        <div className="flex items-center gap-2">
          <Button
            variant={viewMode === "easy" ? "primary" : "outline"}
            onClick={() => setViewMode("easy")}
            className="min-h-[44px]"
            aria-label="Switch to Easy Mode"
          >
            🌱 {t.easyMode}
          </Button>
          <Button
            variant={viewMode === "standard" ? "primary" : "outline"}
            onClick={() => setViewMode("standard")}
            className="min-h-[44px]"
            aria-label="Switch to Standard Mode"
          >
            📊 {t.standardMode}
          </Button>
          <Button
            variant={viewMode === "admin" ? "primary" : "outline"}
            onClick={() => setViewMode("admin")}
            className="min-h-[44px]"
            aria-label="Switch to Admin Dashboard"
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
          <Card className="border-2 border-primary/20 shadow-md">
            <CardHeader className="bg-primary/5">
              <CardTitle className="text-xl flex items-center gap-2">
                🔧 {t.createNew}
              </CardTitle>
              <p className="text-sm text-gray-500">
                Simple, large-target form for quick resident maintenance reporting.
              </p>
            </CardHeader>
            <CardContent className="space-y-4 pt-4">
              <div>
                <label className="block text-sm font-bold mb-1">{t.issueTitle}</label>
                <Input
                  placeholder="e.g. Water leakage near Block C elevator"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="min-h-[48px] text-lg"
                />
              </div>

              <div>
                <Select
                  label={t.categoryLabel}
                  options={categoryOptions}
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  className="min-h-[48px] text-lg"
                />
              </div>

              <div>
                <label className="block text-sm font-bold mb-1">Attach Photo Evidence</label>
                <input
                  type="file"
                  accept="image/*"
                  className="w-full p-2 border rounded min-h-[44px]"
                />
              </div>

              <Button
                className="w-full min-h-[52px] text-lg font-bold bg-emerald-600 hover:bg-emerald-700 text-white"
                onClick={() => {
                  alert("Work Order Submitted Successfully!");
                  setNewTitle("");
                }}
              >
                {t.submitButton}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t.myWorkOrders}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {mockWorkOrders.map((wo) => (
                <div
                  key={wo.id}
                  className="p-4 border rounded-lg hover:bg-accent cursor-pointer flex flex-wrap items-center justify-between gap-2"
                  onClick={() => setSelectedOrder(wo)}
                >
                  <div>
                    <div className="font-mono text-sm font-bold text-muted-foreground">
                      {wo.number}
                    </div>
                    <div className="font-semibold text-lg">{wo.title}</div>
                    <div className="text-sm text-muted-foreground">{wo.category}</div>
                  </div>
                  <div>{getStatusBadge(wo.status)}</div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {/* STANDARD MODE & ADMIN DASHBOARD UI */}
      {viewMode !== "easy" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Work Orders List / Queue */}
          <div className="lg:col-span-2 space-y-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <div>
                  <CardTitle className="text-lg">{t.title}</CardTitle>
                  <p className="text-sm text-gray-500">
                    {viewMode === "admin"
                      ? "Administrative Queue & SLA Monitor"
                      : "Filtered Work Orders List"}
                  </p>
                </div>
                <Button size="sm">➕ New Work Order</Button>
              </CardHeader>
              <CardContent>
                <Table>
                  <thead>
                    <tr className="border-b text-left text-sm font-semibold text-muted-foreground">
                      <th className="py-2">Number</th>
                      <th className="py-2">Title</th>
                      <th className="py-2">Category</th>
                      <th className="py-2">Priority</th>
                      <th className="py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mockWorkOrders.map((wo) => (
                      <tr
                        key={wo.id}
                        className={`border-b cursor-pointer hover:bg-muted/50 ${
                          selectedOrder?.id === wo.id ? "bg-muted font-medium" : ""
                        }`}
                        onClick={() => setSelectedOrder(wo)}
                      >
                        <td className="py-3 font-mono text-xs">{wo.number}</td>
                        <td className="py-3 font-medium">{wo.title}</td>
                        <td className="py-3 text-sm">{wo.category}</td>
                        <td className="py-3">
                          <Badge
                            variant={
                              wo.priority === "CRITICAL"
                                ? "error"
                                : wo.priority === "HIGH"
                                ? "warning"
                                : "default"
                            }
                          >
                            {wo.priority}
                          </Badge>
                        </td>
                        <td className="py-3">{getStatusBadge(wo.status)}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </CardContent>
            </Card>
          </div>

          {/* Work Order Detail / Action Inspector */}
          <div>
            {selectedOrder ? (
              <Card className="sticky top-4">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-muted-foreground font-bold">
                      {selectedOrder.number}
                    </span>
                    {getStatusBadge(selectedOrder.status)}
                  </div>
                  <CardTitle className="text-xl mt-1">{selectedOrder.title}</CardTitle>
                  <p className="text-sm text-gray-500">{selectedOrder.category}</p>
                </CardHeader>

                <CardContent className="space-y-4">
                  <div className="text-sm space-y-2">
                    <div>
                      <span className="text-muted-foreground">{t.priorityLabel}:</span>{" "}
                      <span className="font-bold">{selectedOrder.priority}</span>
                    </div>
                    {selectedOrder.scheduledStart && (
                      <div>
                        <span className="text-muted-foreground">{t.scheduleLabel}:</span>{" "}
                        <span>{selectedOrder.scheduledStart}</span>
                      </div>
                    )}
                    {selectedOrder.assignedTo && (
                      <div>
                        <span className="text-muted-foreground">{t.assignedTo}:</span>{" "}
                        <span className="font-medium">{selectedOrder.assignedTo}</span>
                      </div>
                    )}
                  </div>

                  <Alert title="Operational Material Boundary" variant="info">
                    1x Heavy Duty Rubber Seal gaskets, 2x Brass Connectors logged (Zero Accounting Mutation).
                  </Alert>

                  <div className="border-t pt-3">
                    <div className="text-xs font-bold uppercase text-muted-foreground mb-2">
                      {t.timeline}
                    </div>
                    <div className="space-y-2 text-xs">
                      <div className="flex justify-between text-muted-foreground">
                        <span>• Created via Admin</span>
                        <span>{selectedOrder.createdAt}</span>
                      </div>
                      <div className="flex justify-between text-muted-foreground">
                        <span>• Assigned to Tech Lead</span>
                        <span>Today</span>
                      </div>
                    </div>
                  </div>

                  {viewMode === "admin" && (
                    <div className="border-t pt-3 space-y-2">
                      <Button className="w-full" size="sm">
                        📅 Update Schedule & Priority
                      </Button>
                      <Button className="w-full" variant="outline" size="sm">
                        👤 Reassign Target
                      </Button>
                    </div>
                  )}

                  {selectedOrder.status === "COMPLETED" && (
                    <Button className="w-full bg-emerald-600 hover:bg-emerald-700 text-white">
                      {t.verifyButton}
                    </Button>
                  )}
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="p-6 text-center text-muted-foreground">
                  Select a work order to inspect details and actions.
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </PageContainer>
  );
}
