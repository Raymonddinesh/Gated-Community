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

interface MockAnnouncement {
  id: string;
  announcementNumber: string;
  title: string;
  summary: string;
  body: string;
  priority: "NORMAL" | "IMPORTANT" | "URGENT";
  status: "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "PUBLISHED" | "EXPIRED" | "ARCHIVED";
  authorName: string;
  requiresAcknowledgement: boolean;
  isPinned: boolean;
  publishedAt: string;
  isRead: boolean;
  isAcknowledged: boolean;
  audienceSummary: string;
}

const mockAnnouncements: MockAnnouncement[] = [
  {
    id: "ann-1",
    announcementNumber: "ANN-2026-000001",
    title: "Annual General Body Meeting (AGM) Notice",
    summary: "Schedule, agenda, and mandatory attendance details for the 2026 Society AGM.",
    body: "The Annual General Body Meeting will be held at the Grand Clubhouse on Sunday, Oct 25 at 10:00 AM. Attendance is mandatory for all primary apartment owners.",
    priority: "URGENT",
    status: "PUBLISHED",
    authorName: "Society Management Committee",
    requiresAcknowledgement: true,
    isPinned: true,
    publishedAt: "2026-10-05 09:00",
    isRead: false,
    isAcknowledged: false,
    audienceSummary: "Society Wide (All Owners)",
  },
  {
    id: "ann-2",
    announcementNumber: "ANN-2026-000002",
    title: "Water Tank Cleaning Schedule — Block B",
    summary: "Temporary water supply interruption during quarterly tank disinfection.",
    body: "Overhead and underground water tanks in Block B will undergo deep cleaning on Thursday from 08:00 AM to 02:00 PM. Please store sufficient water.",
    priority: "IMPORTANT",
    status: "PUBLISHED",
    authorName: "Maintenance Operations",
    requiresAcknowledgement: false,
    isPinned: false,
    publishedAt: "2026-10-04 14:00",
    isRead: true,
    isAcknowledged: false,
    audienceSummary: "Block B (All Occupants)",
  },
  {
    id: "ann-3",
    announcementNumber: "ANN-2026-000003",
    title: "Diwali Festival Lighting & Decoration Guidelines",
    summary: "Safety regulations for balcony lights and common area firework celebrations.",
    body: "Residents are requested to use LED string lights only and celebrate fireworks in designated lawn areas under security supervision.",
    priority: "NORMAL",
    status: "PUBLISHED",
    authorName: "Cultural Committee",
    requiresAcknowledgement: false,
    isPinned: false,
    publishedAt: "2026-10-02 11:00",
    isRead: true,
    isAcknowledged: false,
    audienceSummary: "Society Wide (All Residents)",
  },
];

const translations = {
  en: {
    title: "Announcements & Resident Communications",
    subtitle: "Official society notices, targeted updates, mandatory acknowledgements, and broadcast history",
    easyMode: "Easy Mode (Resident)",
    standardMode: "Standard Mode (Detailed)",
    adminMode: "Admin Mode (Publish & Review)",
    newAnnouncement: "+ New Announcement",
    headerActive: "Official Society Announcements",
    headerPending: "Pending Administrative Review",
    headerMetrics: "Read & Acknowledgement Metrics",
    code: "Notice ID",
    titleCol: "Title",
    priority: "Priority",
    audience: "Target Audience",
    publishedAt: "Published At",
    status: "Status",
    actions: "Actions",
    acknowledgeBtn: "Acknowledge Notice",
    acknowledgedBadge: "Acknowledged",
    unreadBadge: "Unread",
    readBadge: "Read",
    urgentNotice: "URGENT NOTICE",
    importantNotice: "IMPORTANT",
    searchPlaceholder: "Search by title, number, or audience...",
    ackWarning: "This announcement requires mandatory explicit acknowledgement.",
  },
  ta: {
    title: "சங்க அறிவிப்புகள் மற்றும் தகவல் தொடர்பு",
    subtitle: "அதிகாரப்பூர்வ அறிவிப்புகள், இலக்கு புதுப்பிப்புகள் மற்றும் ஒப்புதல்கள்",
    easyMode: "எளிய முறை (குடியிருப்பாளர்)",
    standardMode: "நிலையான முறை (விரிவான)",
    adminMode: "நிர்வாக முறை (வெளியீடு & மதிப்பாய்வு)",
    newAnnouncement: "+ புதிய அறிவிப்பு",
    headerActive: "அதிகாரப்பூர்வ சங்க அறிவிப்புகள்",
    headerPending: "நிர்வாக மதிப்பாய்வுக்காக காத்திருக்கிறது",
    headerMetrics: "வாசிப்பு மற்றும் ஒப்புதல் புள்ளிவிவரங்கள்",
    code: "அறிவிப்பு எண்",
    titleCol: "தலைப்பு",
    priority: "முக்கியத்துவம்",
    audience: "இலக்கு பார்வையாளர்கள்",
    publishedAt: "வெளியிடப்பட்ட நேரம்",
    status: "நிலை",
    actions: "செயல்கள்",
    acknowledgeBtn: "ஒப்புதல் அளிக்கவும்",
    acknowledgedBadge: "ஒப்புக்கொள்ளப்பட்டது",
    unreadBadge: "படிக்காதவை",
    readBadge: "படிக்கப்பட்டது",
    urgentNotice: "அவசர அறிவிப்பு",
    importantNotice: "முக்கியமானது",
    searchPlaceholder: "தலைப்பு அல்லது எண் மூலம் தேடுக...",
    ackWarning: "இந்த அறிவிப்பிற்கு கட்டாய ஒப்புதல் தேவைப்படுகிறது.",
  },
};

export default function AnnouncementsPage() {
  const [mode, setMode] = useState<ViewMode>("standard");
  const [lang, setLang] = useState<Language>("en");
  const [searchQuery, setSearchQuery] = useState("");
  const [announcements, setAnnouncements] = useState<MockAnnouncement[]>(mockAnnouncements);

  const t = translations[lang];

  const getPriorityBadge = (priority: MockAnnouncement["priority"]) => {
    switch (priority) {
      case "URGENT":
        return <Badge variant="error">{t.urgentNotice}</Badge>;
      case "IMPORTANT":
        return <Badge variant="warning">{t.importantNotice}</Badge>;
      default:
        return <Badge variant="default">NORMAL</Badge>;
    }
  };

  const handleAcknowledge = (id: string) => {
    setAnnouncements((prev) =>
      prev.map((a) => (a.id === id ? { ...a, isAcknowledged: true, isRead: true } : a))
    );
  };

  const filtered = announcements.filter(
    (a) =>
      a.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.announcementNumber.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.audienceSummary.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <PageContainer>
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t.title}</h1>
          <p className="text-sm text-gray-500">{t.subtitle}</p>
        </div>

        <div className="flex items-center gap-3">
          <Select
            value={lang}
            onChange={(e) => setLang(e.target.value as Language)}
            options={[
              { value: "en", label: "English (EN)" },
              { value: "ta", label: "தமிழ் (TA)" },
            ]}
          />

          <div className="inline-flex rounded-md shadow-sm" role="group">
            <Button
              variant={mode === "easy" ? "primary" : "outline"}
              size="sm"
              onClick={() => setMode("easy")}
            >
              {t.easyMode}
            </Button>
            <Button
              variant={mode === "standard" ? "primary" : "outline"}
              size="sm"
              onClick={() => setMode("standard")}
            >
              {t.standardMode}
            </Button>
            <Button
              variant={mode === "admin" ? "primary" : "outline"}
              size="sm"
              onClick={() => setMode("admin")}
            >
              {t.adminMode}
            </Button>
          </div>
        </div>
      </div>

      {/* EASY MODE */}
      {mode === "easy" && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold">{t.headerActive}</h2>
          </div>

          <div className="grid grid-cols-1 gap-4">
            {filtered.map((a) => (
              <Card key={a.id} className={a.priority === "URGENT" ? "border-2 border-red-500" : ""}>
                <CardHeader className="pb-2">
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        {getPriorityBadge(a.priority)}
                        {!a.isRead && <Badge variant="info">{t.unreadBadge}</Badge>}
                      </div>
                      <CardTitle className="text-lg">{a.title}</CardTitle>
                      <p className="text-xs text-gray-500">{a.audienceSummary} • {a.publishedAt}</p>
                    </div>
                    <span className="font-mono text-xs text-gray-500">{a.announcementNumber}</span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-gray-800 leading-relaxed">{a.body}</p>

                  {a.requiresAcknowledgement && (
                    <div className="p-3 bg-amber-50 border border-amber-200 rounded-md flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                      <span className="text-xs text-amber-900 font-medium">{t.ackWarning}</span>
                      {a.isAcknowledged ? (
                        <Badge variant="success">{t.acknowledgedBadge}</Badge>
                      ) : (
                        <Button size="sm" variant="primary" onClick={() => handleAcknowledge(a.id)}>
                          {t.acknowledgeBtn}
                        </Button>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* STANDARD MODE */}
      {mode === "standard" && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <Input
              placeholder={t.searchPlaceholder}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="max-w-md"
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>{t.headerActive}</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <thead>
                  <tr className="border-b text-left text-xs font-medium text-gray-500 uppercase">
                    <th className="py-2 px-3">{t.code}</th>
                    <th className="py-2 px-3">{t.priority}</th>
                    <th className="py-2 px-3">{t.titleCol}</th>
                    <th className="py-2 px-3">{t.audience}</th>
                    <th className="py-2 px-3">{t.publishedAt}</th>
                    <th className="py-2 px-3">{t.actions}</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-sm">
                  {filtered.map((a) => (
                    <tr key={a.id}>
                      <td className="py-3 px-3 font-mono font-medium text-xs">{a.announcementNumber}</td>
                      <td className="py-3 px-3">{getPriorityBadge(a.priority)}</td>
                      <td className="py-3 px-3 font-medium">
                        <div>
                          <span>{a.title}</span>
                          <p className="text-xs text-gray-500 line-clamp-1">{a.summary}</p>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-xs text-gray-600">{a.audienceSummary}</td>
                      <td className="py-3 px-3 text-xs">{a.publishedAt}</td>
                      <td className="py-3 px-3">
                        {a.requiresAcknowledgement && !a.isAcknowledged ? (
                          <Button size="sm" variant="primary" onClick={() => handleAcknowledge(a.id)}>
                            {t.acknowledgeBtn}
                          </Button>
                        ) : a.requiresAcknowledgement ? (
                          <Badge variant="success">{t.acknowledgedBadge}</Badge>
                        ) : (
                          <Badge variant="info">{t.readBadge}</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ADMIN MODE */}
      {mode === "admin" && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold">{t.adminMode}</h2>
            <Button variant="primary">{t.newAnnouncement}</Button>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>{t.headerMetrics}</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <thead>
                  <tr className="border-b text-left text-xs font-medium text-gray-500 uppercase">
                    <th className="py-2 px-3">{t.code}</th>
                    <th className="py-2 px-3">{t.titleCol}</th>
                    <th className="py-2 px-3">{t.audience}</th>
                    <th className="py-2 px-3">Read Receipts</th>
                    <th className="py-2 px-3">Acknowledgements</th>
                    <th className="py-2 px-3">{t.status}</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-sm">
                  {announcements.map((a) => (
                    <tr key={a.id}>
                      <td className="py-3 px-3 font-mono font-medium text-xs">{a.announcementNumber}</td>
                      <td className="py-3 px-3 font-medium">{a.title}</td>
                      <td className="py-3 px-3 text-xs text-gray-600">{a.audienceSummary}</td>
                      <td className="py-3 px-3 text-xs">85 / 120 (71%)</td>
                      <td className="py-3 px-3 text-xs">{a.requiresAcknowledgement ? "92 / 120 (76%)" : "N/A"}</td>
                      <td className="py-3 px-3">
                        <Badge variant="success">{a.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}
    </PageContainer>
  );
}
