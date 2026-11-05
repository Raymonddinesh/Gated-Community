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

interface MockBooking {
  id: string;
  bookingCode: string;
  facilityName: string;
  title: string;
  requesterName: string;
  startAt: string;
  endAt: string;
  status: "DRAFT" | "PENDING_APPROVAL" | "APPROVED" | "REJECTED" | "CANCELLED" | "CHECKED_IN" | "COMPLETED" | "NO_SHOW" | "EXPIRED";
  participantCount: number;
}

interface MockBlackout {
  id: string;
  facilityName: string;
  title: string;
  startAt: string;
  endAt: string;
  reason: string;
  status: "SCHEDULED" | "ACTIVE" | "COMPLETED" | "CANCELLED";
}

const mockBookings: MockBooking[] = [
  {
    id: "bk-1",
    bookingCode: "BK-2026-000001",
    facilityName: "Grand Clubhouse Banquet Hall",
    title: "Annual Resident Meetup",
    requesterName: "Rajesh Kumar (A-402)",
    startAt: "2026-10-10 18:00",
    endAt: "2026-10-10 22:00",
    status: "APPROVED",
    participantCount: 80,
  },
  {
    id: "bk-2",
    bookingCode: "BK-2026-000002",
    facilityName: "Tennis Court 1",
    title: "Weekend Match",
    requesterName: "Priya Sharma (B-105)",
    startAt: "2026-10-11 07:00",
    endAt: "2026-10-11 09:00",
    status: "PENDING_APPROVAL",
    participantCount: 4,
  },
  {
    id: "bk-3",
    bookingCode: "BK-2026-000003",
    facilityName: "Community Pool Deck",
    title: "Kids Birthday Celebration",
    requesterName: "Senthil Nathan (C-301)",
    startAt: "2026-10-12 16:00",
    endAt: "2026-10-12 19:00",
    status: "CHECKED_IN",
    participantCount: 25,
  },
];

const mockBlackouts: MockBlackout[] = [
  {
    id: "bo-1",
    facilityName: "Olympic Swimming Pool",
    title: "Quarterly Deep Cleaning & Chlorination",
    startAt: "2026-10-15 06:00",
    endAt: "2026-10-16 18:00",
    reason: "Mandatory seasonal water treatment and filtration system maintenance",
    status: "SCHEDULED",
  },
];

const translations = {
  en: {
    title: "Facility Booking & Reservation Management",
    subtitle: "Reserve amenities, manage operating windows, prevent double bookings, and handle check-ins",
    easyMode: "Easy Mode (Resident)",
    standardMode: "Standard Mode (Detailed)",
    adminMode: "Admin Mode (Rules & Approvals)",
    newBooking: "+ Reserve Facility",
    newBlackout: "+ Schedule Blackout",
    bookingsHeader: "Active & Upcoming Reservations",
    blackoutsHeader: "Maintenance & Blackout Periods",
    pendingApprovalsHeader: "Pending Approval Queue",
    bookingCode: "Booking Code",
    facility: "Facility",
    titleCol: "Event Title",
    requester: "Requester",
    timeSlot: "Time Slot",
    status: "Status",
    participants: "Participants",
    actions: "Actions",
    approve: "Approve",
    reject: "Reject",
    cancel: "Cancel",
    checkIn: "Check In",
    complete: "Complete",
    noShow: "No Show",
    searchPlaceholder: "Search by booking code, facility, or resident...",
    doubleBookingAlert: "Strict postgres advisory lock ensures zero double bookings across concurrent reservation requests.",
  },
  ta: {
    title: "வளங்கள் மற்றும் பொது இடங்கள் முன்பதிவு மேலாண்மை",
    subtitle: "வசதிகளை முன்பதிவு செய்தல், இயக்க நேரங்களை நிர்வகித்தல் மற்றும் சரிபார்ப்பு மேற்கொள்தல்",
    easyMode: "எளிய முறை (குடியிருப்பாளர்)",
    standardMode: "நிலையான முறை (விரிவான)",
    adminMode: "நிர்வாக முறை (விதிகள் & ஒப்புதல்கள்)",
    newBooking: "+ வசதி முன்பதிவு செய்க",
    newBlackout: "+ பராமரிப்பு நேரத்தை திட்டமிடுக",
    bookingsHeader: "செயலில் உள்ள மற்றும் வரவிருக்கும் முன்பதிவுகள்",
    blackoutsHeader: "பராமரிப்பு மற்றும் தடை செய்யப்பட்ட காலங்கள்",
    pendingApprovalsHeader: "ஒப்புதலுக்காக காத்திருக்கும் முன்பதிவுகள்",
    bookingCode: "முன்பதிவு குறியீடு",
    facility: "வசதி",
    titleCol: "நிகழ்ச்சி தலைப்பு",
    requester: "முன்பதிவு செய்தவர்",
    timeSlot: "நேர स्लாட்",
    status: "நிலை",
    participants: "பங்கேற்பாளர்கள்",
    actions: "செயல்கள்",
    approve: "ஒப்புதல் அளி",
    reject: "நிராகரி",
    cancel: "ரத்து செய்",
    checkIn: "உள்நுழைவு",
    complete: "நிறைவுறு",
    noShow: "வரவில்லை",
    searchPlaceholder: "குறியீடு, வசதி அல்லது பெயர் மூலம் தேடுக...",
    doubleBookingAlert: "ஒரே நேரத்தில் இரட்டை முன்பதிவு செய்வதை தடுக்க வலுவான பாதுகாப்பு அமைப்பு செயல்படுகிறது.",
  },
};

export default function FacilityBookingsPage() {
  const [mode, setMode] = useState<ViewMode>("standard");
  const [lang, setLang] = useState<Language>("en");
  const [searchQuery, setSearchQuery] = useState("");
  const [bookings, setBookings] = useState<MockBooking[]>(mockBookings);
  const [blackouts] = useState<MockBlackout[]>(mockBlackouts);

  const t = translations[lang];

  const getStatusBadge = (status: MockBooking["status"]) => {
    switch (status) {
      case "APPROVED":
        return <Badge variant="success">APPROVED</Badge>;
      case "PENDING_APPROVAL":
        return <Badge variant="warning">PENDING APPROVAL</Badge>;
      case "CHECKED_IN":
        return <Badge variant="info">CHECKED IN</Badge>;
      case "COMPLETED":
        return <Badge variant="default">COMPLETED</Badge>;
      case "CANCELLED":
        return <Badge variant="error">CANCELLED</Badge>;
      case "REJECTED":
        return <Badge variant="error">REJECTED</Badge>;
      default:
        return <Badge variant="default">{status}</Badge>;
    }
  };

  const handleAction = (id: string, newStatus: MockBooking["status"]) => {
    setBookings((prev) =>
      prev.map((b) => (b.id === id ? { ...b, status: newStatus } : b))
    );
  };

  const filteredBookings = bookings.filter(
    (b) =>
      b.bookingCode.toLowerCase().includes(searchQuery.toLowerCase()) ||
      b.facilityName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      b.requesterName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      b.title.toLowerCase().includes(searchQuery.toLowerCase())
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

      <Alert variant="info" className="mb-6">
        {t.doubleBookingAlert}
      </Alert>

      {/* EASY MODE VIEW */}
      {mode === "easy" && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold">{t.bookingsHeader}</h2>
            <Button variant="primary">{t.newBooking}</Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredBookings.map((b) => (
              <Card key={b.id}>
                <CardHeader className="pb-2">
                  <div className="flex justify-between items-start">
                    <div>
                      <CardTitle className="text-base">{b.title}</CardTitle>
                      <p className="text-xs text-gray-500">{b.facilityName}</p>
                    </div>
                    {getStatusBadge(b.status)}
                  </div>
                </CardHeader>
                <CardContent className="text-sm space-y-2">
                  <div className="flex justify-between text-xs text-gray-600">
                    <span>{t.bookingCode}: <strong>{b.bookingCode}</strong></span>
                    <span>{t.participants}: <strong>{b.participantCount}</strong></span>
                  </div>
                  <div className="text-xs text-gray-600">
                    <span>{t.timeSlot}: </span>
                    <strong className="block text-gray-800">{b.startAt} to {b.endAt}</strong>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* STANDARD MODE VIEW */}
      {mode === "standard" && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <Input
              placeholder={t.searchPlaceholder}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="max-w-md"
            />
            <Button variant="primary">{t.newBooking}</Button>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>{t.bookingsHeader}</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <thead>
                  <tr className="border-b text-left text-xs font-medium text-gray-500 uppercase">
                    <th className="py-2 px-3">{t.bookingCode}</th>
                    <th className="py-2 px-3">{t.facility}</th>
                    <th className="py-2 px-3">{t.titleCol}</th>
                    <th className="py-2 px-3">{t.requester}</th>
                    <th className="py-2 px-3">{t.timeSlot}</th>
                    <th className="py-2 px-3">{t.status}</th>
                    <th className="py-2 px-3">{t.actions}</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-sm">
                  {filteredBookings.map((b) => (
                    <tr key={b.id}>
                      <td className="py-3 px-3 font-mono font-medium text-xs">{b.bookingCode}</td>
                      <td className="py-3 px-3">{b.facilityName}</td>
                      <td className="py-3 px-3 font-medium">{b.title}</td>
                      <td className="py-3 px-3 text-xs text-gray-600">{b.requesterName}</td>
                      <td className="py-3 px-3 text-xs">{b.startAt} - {b.endAt}</td>
                      <td className="py-3 px-3">{getStatusBadge(b.status)}</td>
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-2">
                          {b.status === "APPROVED" && (
                            <Button size="sm" variant="outline" onClick={() => handleAction(b.id, "CHECKED_IN")}>
                              {t.checkIn}
                            </Button>
                          )}
                          {b.status === "CHECKED_IN" && (
                            <Button size="sm" variant="outline" onClick={() => handleAction(b.id, "COMPLETED")}>
                              {t.complete}
                            </Button>
                          )}
                          {["APPROVED", "PENDING_APPROVAL"].includes(b.status) && (
                            <Button size="sm" variant="outline" onClick={() => handleAction(b.id, "CANCELLED")}>
                              {t.cancel}
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ADMIN MODE VIEW */}
      {mode === "admin" && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold">{t.adminMode}</h2>
            <div className="flex gap-2">
              <Button variant="outline">{t.newBlackout}</Button>
              <Button variant="primary">{t.newBooking}</Button>
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>{t.pendingApprovalsHeader}</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <thead>
                  <tr className="border-b text-left text-xs font-medium text-gray-500 uppercase">
                    <th className="py-2 px-3">{t.bookingCode}</th>
                    <th className="py-2 px-3">{t.facility}</th>
                    <th className="py-2 px-3">{t.requester}</th>
                    <th className="py-2 px-3">{t.timeSlot}</th>
                    <th className="py-2 px-3">{t.participants}</th>
                    <th className="py-2 px-3">{t.actions}</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-sm">
                  {bookings
                    .filter((b) => b.status === "PENDING_APPROVAL")
                    .map((b) => (
                      <tr key={b.id}>
                        <td className="py-3 px-3 font-mono font-medium text-xs">{b.bookingCode}</td>
                        <td className="py-3 px-3">{b.facilityName}</td>
                        <td className="py-3 px-3">{b.requesterName}</td>
                        <td className="py-3 px-3 text-xs">{b.startAt} - {b.endAt}</td>
                        <td className="py-3 px-3">{b.participantCount}</td>
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-2">
                            <Button size="sm" variant="primary" onClick={() => handleAction(b.id, "APPROVED")}>
                              {t.approve}
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => handleAction(b.id, "REJECTED")}>
                              {t.reject}
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t.blackoutsHeader}</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <thead>
                  <tr className="border-b text-left text-xs font-medium text-gray-500 uppercase">
                    <th className="py-2 px-3">{t.facility}</th>
                    <th className="py-2 px-3">{t.titleCol}</th>
                    <th className="py-2 px-3">{t.timeSlot}</th>
                    <th className="py-2 px-3">Reason</th>
                    <th className="py-2 px-3">{t.status}</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-sm">
                  {blackouts.map((bo) => (
                    <tr key={bo.id}>
                      <td className="py-3 px-3 font-medium">{bo.facilityName}</td>
                      <td className="py-3 px-3">{bo.title}</td>
                      <td className="py-3 px-3 text-xs">{bo.startAt} - {bo.endAt}</td>
                      <td className="py-3 px-3 text-xs text-gray-600">{bo.reason}</td>
                      <td className="py-3 px-3">
                        <Badge variant="warning">{bo.status}</Badge>
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
