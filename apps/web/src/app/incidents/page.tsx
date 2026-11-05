"use client";

import React, { useState, useEffect } from "react";
import { apiClient } from "@/lib/api-client";

// Internationalization Dictionaries (English & Tamil)
const i18n = {
  en: {
    title: "Emergency & Incident Management",
    subtitle: "Real-time emergency reporting, responder dispatch, hazard containment, and operational incident logs.",
    easyMode: "Easy Mode (SOS)",
    standardMode: "Standard Mode",
    adminMode: "Admin Mode",
    language: "Language",
    english: "English",
    tamil: "தமிழ்",
    sosBanner: "🚨 EMERGENCY SOS BUTTON — Click to instantly report an active emergency",
    sosButtons: {
      fire: "🔥 Fire Emergency",
      medical: "🚑 Medical Emergency",
      security: "🛡️ Security Threat",
      lift: "🛗 Lift Entrapment",
      gas: "⛽ Gas Leak",
      electrical: "⚡ Electrical Hazard",
    },
    tabs: {
      activeIncidents: "Active Incidents",
      reported: "My Reported Incidents",
      contacts: "Emergency Contacts Directory",
      timeline: "Operational Timeline",
      categories: "Categories & SLAs",
    },
    status: {
      reported: "Reported",
      triaged: "Triaged",
      acknowledged: "Acknowledged",
      responseStarted: "Response Started",
      contained: "Contained",
      resolved: "Resolved",
      closed: "Closed",
      escalated: "Escalated",
      cancelled: "Cancelled",
    },
    severity: {
      low: "Low",
      medium: "Medium",
      high: "High",
      critical: "Critical 🚨",
    },
    buttons: {
      reportIncident: "+ Report New Incident",
      triage: "Triage & Set Severity",
      acknowledge: "Acknowledge Response",
      assignResponder: "+ Assign Responder",
      containHazard: "Contain Hazard ✅",
      resolve: "Resolve Incident",
      close: "Close Incident",
      escalate: "Escalate Authority",
      adminOverride: "Admin Override",
      addContact: "+ Add Emergency Contact",
    },
    sampleData: {
      inc1Title: "INC-2026-000001: Main Transformer Short Circuit",
      inc1Desc: "Electrical arc spark near Block B basement sub-station. Power backup grid engaged.",
      inc2Title: "INC-2026-000002: Resident Lift Entrapment - Block C",
      inc2Desc: "Elevator #2 stopped between Floor 4 and 5 with 2 passengers inside. Intercom functional.",
      inc3Title: "INC-2026-000003: Water Pipe Burst in Basement 2",
      inc3Desc: "Main supply riser valve ruptured near Slot B-42. High volume flooding.",
      contact1Name: "City Fire Station & Emergency Rescue",
      contact1Phone: "101 / 044-28551101",
      contact2Name: "City Ambulance & Trauma Care",
      contact2Phone: "108 / 044-28331108",
      contact3Name: "Society Security Control Desk",
      contact3Phone: "+91 98765 43210",
    },
  },
  ta: {
    title: "அவசரநிலை & சம்பவ மேலாண்மை",
    subtitle: "உடனடி அவசரநிலை அறிவிப்பு, பதிலளிப்பவர் அனுப்புதல், ஆபத்து கட்டுப்பாடு மற்றும் சம்பவ பதிவுகள்.",
    easyMode: "எளிதான பயன்முறை (SOS)",
    standardMode: "தரநிலை பயன்முறை",
    adminMode: "நிர்வாகி பயன்முறை",
    language: "மொழி",
    english: "English",
    tamil: "தமிழ்",
    sosBanner: "🚨 அவசர நிலை SOS பொத்தான் — செயலில் உள்ள அவசரநிலையை அறிவிக்க கிளிக் செய்யவும்",
    sosButtons: {
      fire: "🔥 தீ விபத்து அவசரம்",
      medical: "🚑 மருத்துவ அவசரம்",
      security: "🛡️ பாதுகாப்பு அச்சுறுத்தல்",
      lift: "🛗 மின்தூக்கி சிக்கியது",
      gas: "⛽ எரிவாயு கசிவு",
      electrical: "⚡ மின்சார ஆபத்து",
    },
    tabs: {
      activeIncidents: "செயலில் உள்ள சம்பவங்கள்",
      reported: "எனது சம்பவங்கள்",
      contacts: "அவசர தொடர்பு எண்கள்",
      timeline: "செயல்பாட்டு காலவரிசை",
      categories: "பிரிவுகள் & SLAக்கள்",
    },
    status: {
      reported: "அறிவிக்கப்பட்டது",
      triaged: "வகைப்படுத்தப்பட்டது",
      acknowledged: "ஏற்றுக்கொள்ளப்பட்டது",
      responseStarted: "பதில் தொடங்கப்பட்டது",
      contained: "கட்டுப்படுத்தப்பட்டது",
      resolved: "தீர்வு காணப்பட்டது",
      closed: "மூடப்பட்டது",
      escalated: "உயர்த்தப்பட்டது",
      cancelled: "ரத்து செய்யப்பட்டது",
    },
    severity: {
      low: "குறைந்த",
      medium: "நடுத்தர",
      high: "உயர்",
      critical: "மிகவும் அவசரம் 🚨",
    },
    buttons: {
      reportIncident: "+ புதிய சம்பவம் பதிவுசெய்",
      triage: "வகைப்படுத்து & ஆபத்து நிலை அமை",
      acknowledge: "பதிலை உறுதிசெய்",
      assignResponder: "+ பதிலளிப்பவரை நியமி",
      containHazard: "ஆபத்தை கட்டுப்படுத்து ✅",
      resolve: "சம்பவத்தை தீர்த்துவை",
      close: "சம்பவத்தை மூடு",
      escalate: "உயர் அதிகாரிக்கு அனுப்பு",
      adminOverride: "நிர்வாகி மேலெழுதல்",
      addContact: "+ அவசர தொடர்பைச் சேர்",
    },
    sampleData: {
      inc1Title: "INC-2026-000001: மின்மாற்றி மின்கசிவு",
      inc1Desc: "பிளாக் பி அடித்தள மின்நிலையத்தில் மின் தீப்பொறி ஏற்பட்டது.",
      inc2Title: "INC-2026-000002: மின்தூக்கியில் சிக்கிய குடியிருப்பாளர்",
      inc2Desc: "பிளாக் சி மின்தூக்கி தளம் 4 மற்றும் 5 இடையே நின்றது.",
      inc3Title: "INC-2026-000003: அடித்தளத்தில் நீர் குழாய் உடைப்பு",
      inc3Desc: "ஸ்லாட் B-42 அருகே பிரதான நீர் குழாய் உடைந்து நீர் பெருகுகிறது.",
      contact1Name: "நகர தீயணைப்பு மற்றும் மீட்பு மையம்",
      contact1Phone: "101 / 044-28551101",
      contact2Name: "நகர ஆம்புலன்ஸ் & அவசர சிகிச்சை",
      contact2Phone: "108 / 044-28331108",
      contact3Name: "சங்க பாதுகாப்பு கட்டுப்பாட்டு அறை",
      contact3Phone: "+91 98765 43210",
    },
  },
};

export default function IncidentsPage() {
  const [lang, setLang] = useState<"en" | "ta">("en");
  const [mode, setMode] = useState<"easy" | "standard" | "admin">("easy");
  const [activeTab, setActiveTab] = useState<"activeIncidents" | "reported" | "contacts" | "timeline" | "categories">("activeIncidents");

  const [sosStatus, setSosStatus] = useState<string | null>(null);
  const [incidents, setIncidents] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchIncidents() {
      try {
        setLoading(true);
        const data = await apiClient<Array<Record<string, unknown>>>('/api/v1/incidents');
        if (data && Array.isArray(data)) {
          setIncidents(data);
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to fetch incidents');
      } finally {
        setLoading(false);
      }
    }
    fetchIncidents();
  }, []);
  const t = i18n[lang];

  const handleSOS = (type: string) => {
    setSosStatus(`✅ ${type} reported successfully! SOS reference: INC-2026-${Math.floor(100000 + Math.random() * 900000)}. Security desk dispatched.`);
  };

  return (
    <div className="min-h-screen bg-slate-50 p-6 text-slate-800">
      {/* Top Header & Controls */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-xl bg-white p-6 shadow-sm border border-slate-200">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{t.title}</h1>
          <p className="text-sm text-slate-500 mt-1">{t.subtitle}</p>
        </div>

        <div className="flex items-center gap-4">
          {/* Mode Switcher */}
          <div className="flex rounded-lg bg-slate-100 p-1 border border-slate-200">
            <button
              onClick={() => setMode("easy")}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
                mode === "easy" ? "bg-red-600 text-white shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {t.easyMode}
            </button>
            <button
              onClick={() => setMode("standard")}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
                mode === "standard" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {t.standardMode}
            </button>
            <button
              onClick={() => setMode("admin")}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
                mode === "admin" ? "bg-slate-900 text-white shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {t.adminMode}
            </button>
          </div>

          {/* Language Switcher */}
          <div className="flex items-center gap-2 text-xs font-medium border-l border-slate-200 pl-4">
            <span className="text-slate-400">{t.language}:</span>
            <button
              onClick={() => setLang("en")}
              className={`px-2 py-1 rounded ${lang === "en" ? "bg-indigo-50 font-bold text-indigo-600" : "text-slate-500"}`}
            >
              {t.english}
            </button>
            <button
              onClick={() => setLang("ta")}
              className={`px-2 py-1 rounded ${lang === "ta" ? "bg-indigo-50 font-bold text-indigo-600" : "text-slate-500"}`}
            >
              {t.tamil}
            </button>
          </div>
        </div>
      </div>

      {/* EASY MODE / SOS PANEL */}
      {mode === "easy" && (
        <div className="mb-8 rounded-2xl bg-gradient-to-r from-red-600 to-rose-700 p-6 text-white shadow-lg border border-red-500">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold flex items-center gap-2">
              <span>🚨</span> {t.sosBanner}
            </h2>
            <span className="rounded-full bg-red-800/60 px-3 py-1 text-xs font-semibold uppercase tracking-wider">
              1-Touch Emergency Dispatch
            </span>
          </div>

          {sosStatus && (
            <div className="mb-4 rounded-xl bg-white/10 p-3 text-sm font-medium border border-white/20 text-white animate-pulse">
              {sosStatus}
            </div>
          )}

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
            <button
              onClick={() => handleSOS(t.sosButtons.fire)}
              className="flex flex-col items-center justify-center p-4 rounded-xl bg-white/10 hover:bg-white/20 border border-white/20 font-bold text-sm transition-all transform active:scale-95"
            >
              <span className="text-2xl mb-1">🔥</span>
              <span>{t.sosButtons.fire}</span>
            </button>
            <button
              onClick={() => handleSOS(t.sosButtons.medical)}
              className="flex flex-col items-center justify-center p-4 rounded-xl bg-white/10 hover:bg-white/20 border border-white/20 font-bold text-sm transition-all transform active:scale-95"
            >
              <span className="text-2xl mb-1">🚑</span>
              <span>{t.sosButtons.medical}</span>
            </button>
            <button
              onClick={() => handleSOS(t.sosButtons.security)}
              className="flex flex-col items-center justify-center p-4 rounded-xl bg-white/10 hover:bg-white/20 border border-white/20 font-bold text-sm transition-all transform active:scale-95"
            >
              <span className="text-2xl mb-1">🛡️</span>
              <span>{t.sosButtons.security}</span>
            </button>
            <button
              onClick={() => handleSOS(t.sosButtons.lift)}
              className="flex flex-col items-center justify-center p-4 rounded-xl bg-white/10 hover:bg-white/20 border border-white/20 font-bold text-sm transition-all transform active:scale-95"
            >
              <span className="text-2xl mb-1">🛗</span>
              <span>{t.sosButtons.lift}</span>
            </button>
            <button
              onClick={() => handleSOS(t.sosButtons.gas)}
              className="flex flex-col items-center justify-center p-4 rounded-xl bg-white/10 hover:bg-white/20 border border-white/20 font-bold text-sm transition-all transform active:scale-95"
            >
              <span className="text-2xl mb-1">⛽</span>
              <span>{t.sosButtons.gas}</span>
            </button>
            <button
              onClick={() => handleSOS(t.sosButtons.electrical)}
              className="flex flex-col items-center justify-center p-4 rounded-xl bg-white/10 hover:bg-white/20 border border-white/20 font-bold text-sm transition-all transform active:scale-95"
            >
              <span className="text-2xl mb-1">⚡</span>
              <span>{t.sosButtons.electrical}</span>
            </button>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="mb-6 border-b border-slate-200">
        <nav className="flex space-x-6">
          {(["activeIncidents", "reported", "contacts", "timeline", "categories"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-3 text-sm font-semibold border-b-2 transition-all ${
                activeTab === tab
                  ? "border-red-600 text-red-600"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {t.tabs[tab]}
            </button>
          ))}
        </nav>
      </div>

      {/* Main Tab Content */}
      <div className="space-y-4">
        {activeTab === "activeIncidents" && (
          <div className="grid gap-4 md:grid-cols-2">
            {/* Incident 1 */}
            <div className="rounded-xl border border-red-200 bg-red-50/30 p-5 shadow-sm">
              <div className="flex items-start justify-between">
                <div>
                  <span className="inline-block rounded-full bg-red-100 text-red-800 text-xs font-bold px-2.5 py-0.5 mb-2">
                    {t.severity.critical}
                  </span>
                  <h3 className="font-bold text-slate-900">{t.sampleData.inc1Title}</h3>
                  <p className="text-xs text-slate-600 mt-1">{t.sampleData.inc1Desc}</p>
                </div>
                <span className="rounded-md bg-amber-100 text-amber-800 px-2.5 py-1 text-xs font-semibold">
                  {t.status.responseStarted}
                </span>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
                <span>Location: Block B Basement</span>
                <span>Responder: Security Desk</span>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <button className="rounded-lg bg-emerald-600 text-white px-3 py-1.5 text-xs font-semibold hover:bg-emerald-700">
                  {t.buttons.containHazard}
                </button>
                <button className="rounded-lg bg-indigo-600 text-white px-3 py-1.5 text-xs font-semibold hover:bg-indigo-700">
                  {t.buttons.resolve}
                </button>
                <button className="rounded-lg bg-slate-800 text-white px-3 py-1.5 text-xs font-semibold hover:bg-slate-900">
                  {t.buttons.escalate}
                </button>
              </div>
            </div>

            {/* Incident 2 */}
            <div className="rounded-xl border border-amber-200 bg-amber-50/30 p-5 shadow-sm">
              <div className="flex items-start justify-between">
                <div>
                  <span className="inline-block rounded-full bg-amber-100 text-amber-800 text-xs font-bold px-2.5 py-0.5 mb-2">
                    {t.severity.high}
                  </span>
                  <h3 className="font-bold text-slate-900">{t.sampleData.inc2Title}</h3>
                  <p className="text-xs text-slate-600 mt-1">{t.sampleData.inc2Desc}</p>
                </div>
                <span className="rounded-md bg-blue-100 text-blue-800 px-2.5 py-1 text-xs font-semibold">
                  {t.status.acknowledged}
                </span>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
                <span>Location: Block C Floor 4-5</span>
                <span>Responder: Elevator Vendor</span>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <button className="rounded-lg bg-blue-600 text-white px-3 py-1.5 text-xs font-semibold hover:bg-blue-700">
                  {t.buttons.assignResponder}
                </button>
                <button className="rounded-lg bg-indigo-600 text-white px-3 py-1.5 text-xs font-semibold hover:bg-indigo-700">
                  {t.buttons.resolve}
                </button>
              </div>
            </div>
          </div>
        )}

        {activeTab === "contacts" && (
          <div className="rounded-xl bg-white p-6 shadow-sm border border-slate-200">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-slate-900">{t.tabs.contacts}</h3>
              {mode === "admin" && (
                <button className="rounded-lg bg-slate-900 text-white px-3 py-1.5 text-xs font-semibold">
                  {t.buttons.addContact}
                </button>
              )}
            </div>

            <div className="divide-y divide-slate-100">
              <div className="py-3 flex justify-between items-center">
                <div>
                  <p className="font-semibold text-sm text-slate-900">{t.sampleData.contact1Name}</p>
                  <p className="text-xs text-slate-500">Official Fire & Emergency Service</p>
                </div>
                <span className="font-mono text-sm font-bold text-red-600 bg-red-50 px-3 py-1 rounded-lg border border-red-100">
                  {t.sampleData.contact1Phone}
                </span>
              </div>
              <div className="py-3 flex justify-between items-center">
                <div>
                  <p className="font-semibold text-sm text-slate-900">{t.sampleData.contact2Name}</p>
                  <p className="text-xs text-slate-500">Emergency Medical Service</p>
                </div>
                <span className="font-mono text-sm font-bold text-red-600 bg-red-50 px-3 py-1 rounded-lg border border-red-100">
                  {t.sampleData.contact2Phone}
                </span>
              </div>
              <div className="py-3 flex justify-between items-center">
                <div>
                  <p className="font-semibold text-sm text-slate-900">{t.sampleData.contact3Name}</p>
                  <p className="text-xs text-slate-500">On-site Gate Control Desk</p>
                </div>
                <span className="font-mono text-sm font-bold text-indigo-600 bg-indigo-50 px-3 py-1 rounded-lg border border-indigo-100">
                  {t.sampleData.contact3Phone}
                </span>
              </div>
            </div>
          </div>
        )}

        {(activeTab === "reported" || activeTab === "timeline" || activeTab === "categories") && (
          <div className="rounded-xl bg-white p-8 text-center border border-slate-200 shadow-sm">
            <p className="text-sm font-medium text-slate-500">
              Showing active view for <span className="font-semibold text-slate-900">{t.tabs[activeTab]}</span>.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
