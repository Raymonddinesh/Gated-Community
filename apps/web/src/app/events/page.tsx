"use client";

import React, { useState, useEffect } from "react";
import { apiClient } from "@/lib/api-client";

// Internationalization Dictionaries (English & Tamil)
const i18n = {
  en: {
    title: "Events & Community Activities",
    subtitle: "Discover, register, and participate in society cultural, sports, and festival events.",
    easyMode: "Easy Mode",
    standardMode: "Standard Mode",
    adminMode: "Admin Mode",
    language: "Language",
    english: "English",
    tamil: "தமிழ்",
    filterAll: "All Events",
    filterCultural: "Cultural",
    filterSports: "Sports",
    filterFestival: "Festival",
    filterWorkshop: "Workshop",
    filterAwareness: "Awareness",
    filterCommunity: "Community",
    createEvent: "+ Create Event",
    registeredCount: "registered",
    capacityFull: "Waitlist Only",
    registerNow: "REGISTER NOW",
    alreadyRegistered: "REGISTERED",
    cancelRegistration: "Cancel Registration",
    eventStatus: "Status",
    eventDate: "Date & Time",
    location: "Location",
    capacity: "Capacity",
    actions: "Actions",
    approve: "Approve",
    reject: "Reject",
    publish: "Publish",
    cancelEvent: "Cancel Event",
    recordAttendance: "Mark Attended",
    markNoShow: "Mark No-Show",
    myRegistrations: "My Registrations",
    metricsTitle: "Event Statistics",
    totalRegistered: "Total Registered",
    confirmed: "Confirmed",
    waitlisted: "Waitlisted",
    attended: "Attended",
    pongalTitle: "🎉 Pongal Celebration & Cultural Fest",
    pongalDesc: "Join us for traditional Pongal cooking, rangoli contest, and evening cultural dance performances.",
    sportsTitle: "🏆 Annual Society Badminton Tournament",
    sportsDesc: "Men's, Women's, and Junior doubles badminton tournament at the Indoor Sports Hall.",
  },
  ta: {
    title: "நிகழ்வுகள் & சமுதாய செயல்பாடுகள்",
    subtitle: "சமுதாய கலாச்சார, விளையாட்டு மற்றும் திருவிழா நிகழ்வுகளில் பங்கேற்கவும் பதிவு செய்யவும்.",
    easyMode: "எளிய முறை",
    standardMode: "நிலையான முறை",
    adminMode: "நிர்வாகி முறை",
    language: "மொழி",
    english: "English",
    tamil: "தமிழ்",
    filterAll: "எல்லா நிகழ்வுகளும்",
    filterCultural: "கலாச்சாரம்",
    filterSports: "விளையாட்டு",
    filterFestival: "திருவிழா",
    filterWorkshop: "பயிற்சிப்பட்டறை",
    filterAwareness: "விழிப்புணர்வு",
    filterCommunity: "சமுதாயம்",
    createEvent: "+ புதிய நிகழ்வு",
    registeredCount: "பதிவு செய்யப்பட்டுள்ளது",
    capacityFull: "காத்திருப்பு பட்டியல் மட்டும்",
    registerNow: "இப்பொழுதே பதிவு செய்",
    alreadyRegistered: "பதிவு செய்யப்பட்டது",
    cancelRegistration: "பதிவை ரத்து செய்",
    eventStatus: "நிலை",
    eventDate: "தேதி & நேரம்",
    location: "இடம்",
    capacity: "கொள்ளளவு",
    actions: "செயல்கள்",
    approve: "ஒப்புதல் அளி",
    reject: "நிராகரி",
    publish: "வெளியிடு",
    cancelEvent: "நிகழ்வை ரத்து செய்",
    recordAttendance: "வருகையை பதிவு செய்",
    markNoShow: "வராதவராக பதிவு செய்",
    myRegistrations: "எனது பதிவுகள்",
    metricsTitle: "நிகழ்வு புள்ளிவிவரங்கள்",
    totalRegistered: "மொத்த பதிவுகள்",
    confirmed: "உறுதி செய்யப்பட்டது",
    waitlisted: "காத்திருப்பு பட்டியல்",
    attended: "பங்கேற்றோர்",
    pongalTitle: "🎉 பொங்கல் பெருவிழா & கலாச்சார கொண்டாட்டம்",
    pongalDesc: "பாரம்பரிய பொங்கல் வைத்தால், கோலப் போட்டி மற்றும் மாலை கலை நிகழ்ச்சிகளில் பங்கேற்கவும்.",
    sportsTitle: "🏆 ஆண்டறிக்கை பேட்மிண்டன் போட்டி",
    sportsDesc: "உள்விளையாட்டு அரங்கில் நடைபெறும் பேட்மிண்டன் போட்டிகள்.",
  },
};

type ViewMode = "easy" | "standard" | "admin";
type Lang = "en" | "ta";

export default function EventsPage() {
  const [lang, setLang] = useState<Lang>("en");
  const [viewMode, setViewMode] = useState<ViewMode>("easy");
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [userRegistrations, setUserRegistrations] = useState<Record<string, boolean>>({
    "evt-1": true,
  });
  const [eventsList, setEventsList] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchEvents() {
      try {
        setLoading(true);
        const data = await apiClient<Array<Record<string, unknown>>>('/api/v1/events');
        if (data && Array.isArray(data)) {
          setEventsList(data);
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to fetch events');
      } finally {
        setLoading(false);
      }
    }
    fetchEvents();
  }, []);

  const t = i18n[lang];

  const dummyEvents = [
    {
      id: "evt-1",
      number: "EVT-2026-000001",
      title: t.pongalTitle,
      description: t.pongalDesc,
      type: "FESTIVAL",
      status: "PUBLISHED",
      date: "Jan 15, 2026 • 06:00 PM - 09:00 PM",
      location: "Community Hall & Garden",
      registered: 72,
      capacity: 100,
    },
    {
      id: "evt-2",
      number: "EVT-2026-000002",
      title: t.sportsTitle,
      description: t.sportsDesc,
      type: "SPORTS",
      status: "REGISTRATION_OPEN",
      date: "Feb 08, 2026 • 08:00 AM - 05:00 PM",
      location: "Indoor Sports Complex",
      registered: 32,
      capacity: 40,
    },
  ];

  const toggleRegister = (id: string) => {
    setUserRegistrations((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 p-4 sm:p-6 md:p-8">
      {/* Header & Controls */}
      <header className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center md:justify-between border-b border-slate-200 dark:border-slate-800 pb-6 mb-8 gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-indigo-600 dark:text-indigo-400">
            {t.title}
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">{t.subtitle}</p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Mode Switcher */}
          <div className="bg-slate-200 dark:bg-slate-800 p-1 rounded-lg flex items-center gap-1 text-xs font-semibold">
            <button
              onClick={() => setViewMode("easy")}
              className={`px-3 py-1.5 rounded-md transition-colors ${
                viewMode === "easy"
                  ? "bg-white dark:bg-indigo-600 text-indigo-600 dark:text-white shadow-sm"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
              }`}
            >
              {t.easyMode}
            </button>
            <button
              onClick={() => setViewMode("standard")}
              className={`px-3 py-1.5 rounded-md transition-colors ${
                viewMode === "standard"
                  ? "bg-white dark:bg-indigo-600 text-indigo-600 dark:text-white shadow-sm"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
              }`}
            >
              {t.standardMode}
            </button>
            <button
              onClick={() => setViewMode("admin")}
              className={`px-3 py-1.5 rounded-md transition-colors ${
                viewMode === "admin"
                  ? "bg-white dark:bg-indigo-600 text-indigo-600 dark:text-white shadow-sm"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
              }`}
            >
              {t.adminMode}
            </button>
          </div>

          {/* Language Switcher */}
          <div className="flex items-center gap-1 bg-slate-200 dark:bg-slate-800 p-1 rounded-lg text-xs font-semibold">
            <button
              onClick={() => setLang("en")}
              className={`px-2.5 py-1 rounded ${
                lang === "en" ? "bg-indigo-600 text-white" : "text-slate-600 dark:text-slate-400"
              }`}
            >
              {t.english}
            </button>
            <button
              onClick={() => setLang("ta")}
              className={`px-2.5 py-1 rounded ${
                lang === "ta" ? "bg-indigo-600 text-white" : "text-slate-600 dark:text-slate-400"
              }`}
            >
              {t.tamil}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto">
        {/* EASY MODE UI */}
        {viewMode === "easy" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {dummyEvents.map((evt) => {
              const isRegistered = !!userRegistrations[evt.id];
              return (
                <div
                  key={evt.id}
                  className="bg-white dark:bg-slate-800 rounded-2xl shadow-md border border-slate-200 dark:border-slate-700 overflow-hidden flex flex-col justify-between"
                >
                  <div className="p-6">
                    <div className="flex items-center justify-between gap-2 mb-3">
                      <span className="px-3 py-1 bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 text-xs font-bold rounded-full uppercase tracking-wider">
                        {evt.type}
                      </span>
                      <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                        {evt.registered} / {evt.capacity} {t.registeredCount}
                      </span>
                    </div>

                    <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">
                      {evt.title}
                    </h2>
                    <p className="text-slate-600 dark:text-slate-300 text-sm mb-4 leading-relaxed">
                      {evt.description}
                    </p>

                    <div className="space-y-2 text-xs text-slate-500 dark:text-slate-400">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-700 dark:text-slate-300">
                          {t.eventDate}:
                        </span>
                        <span>{evt.date}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-700 dark:text-slate-300">
                          {t.location}:
                        </span>
                        <span>{evt.location}</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-6 pt-0">
                    <button
                      onClick={() => toggleRegister(evt.id)}
                      aria-label={isRegistered ? t.cancelRegistration : t.registerNow}
                      className={`w-full py-3.5 px-6 rounded-xl font-bold text-sm tracking-wide transition-all shadow-md ${
                        isRegistered
                          ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                          : "bg-indigo-600 hover:bg-indigo-700 text-white"
                      }`}
                    >
                      {isRegistered ? `✓ ${t.alreadyRegistered} (${t.cancelRegistration})` : t.registerNow}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* STANDARD MODE UI */}
        {viewMode === "standard" && (
          <div className="space-y-6">
            {/* Filter Bar */}
            <div className="flex flex-wrap items-center justify-between gap-4 bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700">
              <div className="flex flex-wrap items-center gap-2">
                {["ALL", "CULTURAL", "SPORTS", "FESTIVAL", "WORKSHOP"].map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setSelectedCategory(cat)}
                    className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      selectedCategory === cat
                        ? "bg-indigo-600 text-white"
                        : "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-200"
                    }`}
                  >
                    {cat === "ALL" ? t.filterAll : cat}
                  </button>
                ))}
              </div>
            </div>

            {/* Event Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {dummyEvents.map((evt) => (
                <div
                  key={evt.id}
                  className="bg-white dark:bg-slate-800 rounded-xl p-5 border border-slate-200 dark:border-slate-700 shadow-sm"
                >
                  <div className="text-xs font-mono text-indigo-500 mb-1">{evt.number}</div>
                  <h3 className="font-bold text-lg mb-2 text-slate-900 dark:text-white">
                    {evt.title}
                  </h3>
                  <p className="text-xs text-slate-600 dark:text-slate-400 mb-4 line-clamp-2">
                    {evt.description}
                  </p>
                  <div className="text-xs space-y-1 text-slate-500 border-t border-slate-100 dark:border-slate-700 pt-3">
                    <div>📅 {evt.date}</div>
                    <div>📍 {evt.location}</div>
                    <div>👥 {evt.registered} / {evt.capacity} {t.registeredCount}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ADMIN MODE UI */}
        {viewMode === "admin" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700">
              <div>
                <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                  Event Administration & Approvals
                </h2>
                <p className="text-xs text-slate-500">
                  Manage society event lifecycle, review approvals, publish events, and track attendance.
                </p>
              </div>
              <button className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs px-4 py-2.5 rounded-lg shadow-sm">
                {t.createEvent}
              </button>
            </div>

            {/* Admin Table */}
            <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-x-auto shadow-sm">
              <table className="w-full text-left text-xs text-slate-700 dark:text-slate-300">
                <thead className="bg-slate-100 dark:bg-slate-700/50 text-slate-900 dark:text-white uppercase font-bold text-[10px] tracking-wider">
                  <tr>
                    <th className="p-3.5">Event No</th>
                    <th className="p-3.5">Title</th>
                    <th className="p-3.5">Type</th>
                    <th className="p-3.5">Status</th>
                    <th className="p-3.5">Registered</th>
                    <th className="p-3.5">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-700 font-medium">
                  {dummyEvents.map((evt) => (
                    <tr key={evt.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                      <td className="p-3.5 font-mono text-indigo-600 dark:text-indigo-400">
                        {evt.number}
                      </td>
                      <td className="p-3.5 font-bold text-slate-900 dark:text-white">
                        {evt.title}
                      </td>
                      <td className="p-3.5">{evt.type}</td>
                      <td className="p-3.5">
                        <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 font-semibold">
                          {evt.status}
                        </span>
                      </td>
                      <td className="p-3.5">{evt.registered} / {evt.capacity}</td>
                      <td className="p-3.5 space-x-2">
                        <button className="px-2.5 py-1 bg-indigo-600 text-white rounded text-[11px] hover:bg-indigo-700">
                          {t.publish}
                        </button>
                        <button className="px-2.5 py-1 bg-emerald-600 text-white rounded text-[11px] hover:bg-emerald-700">
                          {t.recordAttendance}
                        </button>
                        <button className="px-2.5 py-1 bg-rose-600 text-white rounded text-[11px] hover:bg-rose-700">
                          {t.cancelEvent}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
